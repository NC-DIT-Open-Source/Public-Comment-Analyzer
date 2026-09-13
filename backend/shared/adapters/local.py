"""Private local files and transactional SQLite jobs and background tasks.

Run one application process per data directory. A process lock rejects accidental
multiple workers. Pending work survives restart; interrupted inference is marked
failed rather than silently repeating paid or nondeterministic model calls.
"""

from contextlib import contextmanager
import hashlib
import hmac
import importlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlencode
import uuid

if __package__ == 'backend.shared.adapters':
    from ..runtime import RuntimeConfigurationError, StorageError, positive_int
else:
    from runtime import RuntimeConfigurationError, StorageError, positive_int

logger = logging.getLogger(__name__)


def canonical_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise StorageError("INVALID_ID", "A valid UUID is required") from exc
    if parsed.version != 4 or str(parsed) != value.lower():
        raise StorageError("INVALID_ID", "A canonical version 4 UUID is required")
    return str(parsed)


def valid_key(key: str) -> str:
    if not isinstance(key, str):
        raise StorageError("INVALID_KEY", "Invalid object key")
    parts = PurePosixPath(key).parts
    if len(parts) != 3 or parts[0] not in {"uploads", "results"}:
        raise StorageError("INVALID_KEY", "Invalid object key")
    canonical_id(parts[1])
    expected = "input" if parts[0] == "uploads" else "output"
    if parts[2] not in {f"{expected}.csv", f"{expected}.xlsx"} or "/".join(parts) != key:
        raise StorageError("INVALID_KEY", "Invalid object key")
    return key


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeConfigurationError("Data directories must not be symbolic links")
    path.chmod(0o700)


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root / "objects"
        _private_directory(self.root)
        self._lock = threading.Lock()
        self.max_bytes = positive_int("APP_MAX_STORAGE_BYTES", 1024**3, 1024**4)
        secret_path = root / "download.key"
        try:
            fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as secret:
                secret.write(secrets.token_bytes(32))
                secret.flush()
                os.fsync(secret.fileno())
        if secret_path.is_symlink():
            raise RuntimeConfigurationError("Download signing key must not be a symbolic link")
        self._secret = secret_path.read_bytes()
        if len(self._secret) != 32:
            raise RuntimeConfigurationError("Invalid download signing key")

    def path(self, key: str) -> Path:
        key = valid_key(key)
        result = self.root.joinpath(*key.split("/"))
        for parent in (result, *result.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                raise StorageError("INVALID_KEY", "Symbolic links are not allowed")
        if not result.resolve().is_relative_to(self.root.resolve()):
            raise StorageError("INVALID_KEY", "Invalid object key")
        return result

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
        del content_type
        if not isinstance(body, bytes):
            raise StorageError("INVALID_OBJECT", "Object contents must be bytes")
        with self._lock:
            path = self.path(key)
            used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file() and not p.is_symlink())
            previous = path.stat().st_size if path.exists() else 0
            if used - previous + len(body) > self.max_bytes:
                raise StorageError("STORAGE_FULL", "Local storage capacity reached")
            _private_directory(path.parent)
            fd, staging = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(staging, path)
            finally:
                if os.path.exists(staging):
                    os.unlink(staging)

    def upload(self, path: str, key: str) -> None:
        self.put(key, Path(path).read_bytes())

    def download(self, key: str, path: str) -> None:
        source = self.path(key)
        if not source.is_file():
            raise StorageError("NoSuchKey", "The requested file was not found")
        shutil.copyfile(source, path)

    def signed_url(self, key: str, expires: int = 3600) -> str:
        valid_key(key)
        if not key.startswith("results/") or not 1 <= expires <= 3600:
            raise StorageError("INVALID_DOWNLOAD", "Invalid download request")
        if not self.exists(key):
            raise StorageError("NoSuchKey", "The requested file was not found")
        deadline = int(time.time()) + expires
        signature = self._signature(key, deadline)
        return "/api/download?" + urlencode({"key": key, "expires": deadline, "signature": signature})

    def _signature(self, key: str, deadline: int) -> str:
        return hmac.new(self._secret, f"{key}\n{deadline}".encode(), hashlib.sha256).hexdigest()

    def verify_download(self, key: str, deadline: int, signature: str) -> Path:
        valid_key(key)
        if not isinstance(signature, str) or not re.fullmatch(r'[0-9a-f]{64}', signature):
            raise StorageError('INVALID_DOWNLOAD', 'Download link is invalid or expired')
        if not key.startswith("results/") or deadline <= time.time() or deadline > time.time() + 3600:
            raise StorageError("INVALID_DOWNLOAD", "Download link is invalid or expired")
        if not hmac.compare_digest(self._signature(key, deadline), signature):
            raise StorageError("INVALID_DOWNLOAD", "Download link is invalid or expired")
        path = self.path(key)
        if not path.is_file():
            raise StorageError("NoSuchKey", "The requested file was not found")
        return path


class LocalJobStore:
    def __init__(self, database: Path):
        self.database = database
        if database.is_symlink():
            raise RuntimeConfigurationError("Job database must not be a symbolic link")
        self.max_active = positive_int("APP_MAX_ACTIVE_JOBS", 8, 1000)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL
                );
            """)
        database.chmod(0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database, timeout=30)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, job_id: str):
        job_id = canonical_id(job_id)
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, item: dict) -> None:
        job_id = canonical_id(item["jobId"])
        self.expire()
        item = dict(item)
        item.setdefault('ttl', int(time.time()) + positive_int('APP_JOB_TTL_SECONDS', 604800, 2592000))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute("SELECT COUNT(*) FROM jobs WHERE json_extract(body,'$.status') NOT IN ('completed','failed')").fetchone()[0]
            if active >= self.max_active:
                raise StorageError("QUEUE_FULL", "Too many active jobs; finish an existing job first")
            try:
                conn.execute("INSERT INTO jobs(id,body) VALUES (?,?)", (job_id, json.dumps(item)))
            except sqlite3.IntegrityError as exc:
                raise StorageError("JOB_EXISTS", "Job already exists") from exc

    def update(self, job_id: str, fields: dict) -> None:
        job_id = canonical_id(job_id)
        if "jobId" in fields and fields["jobId"] != job_id:
            raise StorageError("INVALID_JOB", "Job ID cannot change")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise StorageError("JOB_NOT_FOUND", "Job not found")
            item = json.loads(row[0])
            item.update(fields)
            conn.execute("UPDATE jobs SET body=? WHERE id=?", (json.dumps(item), job_id))

    def claim_preview(self, job_id: str) -> bool:
        job_id = canonical_id(job_id)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return False
            item = json.loads(row[0])
            if item.get("status") != "preview_ready":
                return False
            item["status"] = "processing"
            conn.execute("UPDATE jobs SET body=? WHERE id=?", (json.dumps(item), job_id))
            return True

    def cancel(self, job_id):
        job_id = canonical_id(job_id)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                return False
            item = json.loads(row[0])
            running = conn.execute("SELECT 1 FROM tasks WHERE id LIKE ? AND state='running'", (f'row_processor:{job_id}:%',)).fetchone()
            if running or item.get('status') not in {'pending', 'preview_ready'}:
                return False
            item.update(status='failed', errors=[{'message': 'Cancelled by the user.', 'errorType': 'Cancelled'}])
            conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))
            conn.execute("UPDATE tasks SET state='cancelled' WHERE id LIKE ? AND state='pending'", (f'row_processor:{job_id}:%',))
            return True

    def expire(self):
        """Release abandoned job slots while retaining all source/result files."""
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute("SELECT id,body FROM jobs WHERE json_extract(body,'$.status') NOT IN ('completed','failed') AND json_extract(body,'$.ttl') <= ?", (time.time(),)).fetchall()
            for job_id, body in rows:
                item = json.loads(body)
                item.update(status='failed', errors=[{'message': 'The job expired before it completed.', 'errorType': 'Expired'}])
                conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))
                conn.execute("UPDATE tasks SET state='cancelled' WHERE id LIKE ? AND state='pending'", (f'row_processor:{job_id}:%',))

    def increment(self, job_id, field, amount):
        if field != 'completedRows' or not isinstance(amount, int):
            raise StorageError('INVALID_UPDATE', 'Invalid counter update')
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                raise StorageError('JOB_NOT_FOUND', 'Job not found')
            item = json.loads(row[0])
            item[field] = item.get(field, 0) + amount
            conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))

    def append_error(self, job_id, error):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                return
            item = json.loads(row[0])
            item.setdefault('errors', []).append(error)
            conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))


class LocalRuntime:
    def __init__(self, root: Path):
        _private_directory(root)
        self.root = root
        self.objects = LocalObjectStore(root)
        self.jobs = LocalJobStore(root / "jobs.sqlite3")
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker = None
        self._process_lock = None

    def enqueue(self, name: str, payload: dict) -> None:
        job_id = payload.get("jobId") or (payload.get("pathParameters") or {}).get("jobId")
        job_id = canonical_id(job_id)
        phase = payload.get("phase", "full") if name == "row_processor" else "summary"
        task_id = f"{name}:{job_id}:{phase}"
        with self.jobs.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO tasks VALUES (?,?,?,?,?)", (
                task_id, name, json.dumps(payload), "pending", time.time()))
        self._wake.set()

    def _claim(self):
        with self.jobs.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id,name,body FROM tasks WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE tasks SET state='running' WHERE id=?", (row[0],))
            return row

    def _fail_task(self, name: str, payload: dict, reason: str) -> None:
        job_id = payload.get("jobId") or (payload.get("pathParameters") or {}).get("jobId")
        item = self.jobs.get(job_id)
        if not item:
            return
        if name == "aggregate_analyzer":
            self.jobs.update(job_id, {"analysisStatus": "failed", "analysisError": reason})
        else:
            self.jobs.update(job_id, {"status": "failed", "errors": [{"message": reason, "errorType": "TaskInterrupted"}]})

    def recover(self):
        self.jobs.expire()
        with self.jobs.connect() as conn:
            interrupted = conn.execute("SELECT id,name,body FROM tasks WHERE state='running'").fetchall()
            conn.execute("UPDATE tasks SET state='failed' WHERE state='running'")
        for task_id, name, body in interrupted:
            payload = json.loads(body)
            job_id = payload.get('jobId') or (payload.get('pathParameters') or {}).get('jobId')
            item = self.jobs.get(job_id) or {}
            saved = False
            if name == 'row_processor':
                if payload.get('phase', 'full') == 'preview':
                    saved = item.get('status') == 'preview_ready' and bool(item.get('previewRows'))
                elif item.get('status') == 'completed' and item.get('outputFileKey'):
                    try:
                        saved = self.objects.exists(item['outputFileKey'])
                    except StorageError:
                        saved = False
            elif name == 'aggregate_analyzer':
                saved = item.get('status') == 'completed' and bool(item.get('aggregateAnalysis'))
            if saved:
                # Output/state can commit just before the queue acknowledgment.
                # Preserve that proven result; never repeat its paid inference.
                with self.jobs.connect() as conn:
                    conn.execute("UPDATE tasks SET state='done' WHERE id=?", (task_id,))
            else:
                self._fail_task(name, payload, "Processing was interrupted. Review the job before starting a new analysis.")
        # Persisting a job/preview claim and dispatching it are separate actions.
        # A crash between them must become visible instead of leaving a spinner.
        with self.jobs.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            candidates = conn.execute("SELECT id,body FROM jobs WHERE json_extract(body,'$.status') IN ('pending','processing','preview_processing')").fetchall()
            for job_id, body in candidates:
                queued = conn.execute("SELECT 1 FROM tasks WHERE id LIKE ? AND state IN ('pending','running')", (f'row_processor:{job_id}:%',)).fetchone()
                if not queued:
                    item = json.loads(body)
                    item.update(status='failed', errors=[{'message': 'Processing was interrupted before it could be scheduled.', 'errorType': 'TaskInterrupted'}])
                    conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))
            completed = conn.execute("SELECT id,body FROM jobs WHERE json_extract(body,'$.status')='completed'").fetchall()
            for job_id, body in completed:
                item = json.loads(body)
                queued = conn.execute("SELECT 1 FROM tasks WHERE id=?", (f'aggregate_analyzer:{job_id}:summary',)).fetchone()
                if not item.get('aggregateAnalysis') and not queued:
                    item.update(analysisStatus='failed', analysisError='The summary was interrupted before it could be scheduled.')
                    conn.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(item), job_id))

    def run_one(self) -> bool:
        task = self._claim()
        if not task:
            return False
        task_id, name, body = task
        payload = json.loads(body)
        state = "done"
        try:
            if name not in {"row_processor", "aggregate_analyzer"}:
                raise StorageError("INVALID_TASK", "Unknown task")
            module = importlib.import_module(f"backend.{name}.handler")
            response = module.lambda_handler(payload, SimpleNamespace(function_name=name, request_id="local"))
            if response.get("statusCode", 500) >= 400:
                state = "failed"
                self._fail_task(name, payload, "Processing failed. Review the job before starting a new analysis.")
        except Exception:
            # Provider errors can contain request text and credentials; do not log them.
            logger.error("A background task failed")
            state = "failed"
            self._fail_task(name, payload, "Processing failed. Review the job before starting a new analysis.")
        finally:
            with self.jobs.connect() as conn:
                conn.execute("UPDATE tasks SET state=? WHERE id=?", (state, task_id))
        return True

    def start(self):
        if self._worker and self._worker.is_alive():
            raise RuntimeConfigurationError("Only one application worker may use a data directory")
        lock_path = self.root / "worker.lock"
        if lock_path.is_symlink():
            raise RuntimeConfigurationError("Worker lock must not be a symbolic link")
        handle = open(lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeConfigurationError("Only one application worker may use a data directory") from exc
        self._process_lock = handle
        self.recover()
        self._stop.clear()

        def work():
            try:
                while not self._stop.is_set():
                    if not self.run_one():
                        self._wake.wait(0.5)
                        self._wake.clear()
            finally:
                handle.close()
        self._worker = threading.Thread(target=work, name="analysis-worker", daemon=True)
        self._worker.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=10)

    def healthy(self):
        return bool(self._worker and self._worker.is_alive() and not self._stop.is_set())
