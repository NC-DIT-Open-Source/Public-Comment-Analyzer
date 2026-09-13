"""Serve the existing HTTP contract and built frontend without cloud services.

Start with: uvicorn backend.local.app:app --host 127.0.0.1 --port 8000
Use a single process per mounted data directory; put HTTPS at the ingress.
"""

from collections import OrderedDict, deque
from contextlib import asynccontextmanager
import asyncio
import base64
import importlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from types import SimpleNamespace

import bcrypt
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from auth import validate_access_key
from runtime import get_password_hash, get_runtime, positive_int, runtime_name, RuntimeConfigurationError, StorageError

_JOB_ROUTE = re.compile(r"^(status|results|dashboard|process)/([0-9a-fA-F-]{36})(/preview-confirm|/cancel)?$")


def error_response(code: str, message: str, status: int):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _static_asset_manifest() -> dict[str, Path]:
    """Enumerate trusted build files once; requests only select manifest keys."""
    root = Path(os.environ.get('APP_STATIC_DIR', 'frontend/dist/public-comment-app/browser')).resolve()
    assets = {}
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        parent = Path(directory)
        subdirectories[:] = [name for name in subdirectories
                             if not name.startswith('.') and not (parent / name).is_symlink()]
        for filename in filenames:
            if filename.startswith('.'):
                continue
            candidate = parent / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved.is_relative_to(root):
                assets[candidate.relative_to(root).as_posix()] = resolved
    return assets


class RateLimiter:
    """Bounded process-local admission control; ingress limits add another layer."""
    def __init__(self):
        self._buckets = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, maximum: int) -> bool:
        now = time.monotonic()
        with self._lock:
            if key not in self._buckets and len(self._buckets) >= 4096:
                self._buckets.popitem(last=False)
            bucket = self._buckets.setdefault(key, deque())
            self._buckets.move_to_end(key)
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= maximum:
                return False
            bucket.append(now)
            return True


def _validate_process_body(body):
    """Reject malformed shapes before existing domain validation or paid work."""
    for name in ("fileId", "selectedCommentColumn", "contextDescription"):
        if not isinstance(body.get(name), str):
            raise ValueError("Required fields must be strings")
    columns = body.get("analysisColumns")
    if not isinstance(columns, list) or not columns or len(columns) > 20:
        raise ValueError("Provide between 1 and 20 analysis columns")
    names = set()
    for col in columns:
        if not isinstance(col, dict) or not isinstance(col.get("name"), str):
            raise ValueError("Each analysis column requires a name")
        name = col["name"]
        if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', name):
            raise ValueError('Analysis column names cannot contain control characters')
        if not name.strip() or name.lower() in names or name == "_error":
            raise ValueError("Analysis column names must be unique and cannot be _error")
        names.add(name.lower())
        if col.get("type", "open_text") not in {"open_text", "categorized"}:
            raise ValueError("Unknown analysis column type")
        if not isinstance(col.get("instructions", ""), str):
            raise ValueError("Instructions must be text")
        options = col.get("options", [])
        if not isinstance(options, list) or len(options) > 50:
            raise ValueError("Invalid category options")
        option_values = set()
        for option in options:
            if not isinstance(option, dict) or not isinstance(option.get("value"), str) or not isinstance(option.get("description"), str):
                raise ValueError("Category options require a value and description")
            if len(option["value"]) > 200 or len(option["description"]) > 2000 or option["value"].casefold() in option_values:
                raise ValueError("Category options must be bounded and distinct")
            option_values.add(option["value"].casefold())
        examples = col.get("examples") or []
        if not isinstance(examples, list) or len(examples) > 14:
            raise ValueError("Invalid category examples")
        for example in examples:
            if not isinstance(example, dict) or not isinstance(example.get("commentText"), str) or not isinstance(example.get("label"), str):
                raise ValueError("Examples require commentText and label strings")


def create_app(*, start_worker: bool = True):
    limiter = RateLimiter()
    max_requests = positive_int("APP_MAX_REQUESTS_PER_MINUTE", 180, 10000)
    max_expensive = positive_int("APP_MAX_ANALYSES_PER_MINUTE", 12, 1000)
    max_body = positive_int("APP_MAX_REQUEST_BYTES", 101 * 1024 * 1024, 101 * 1024 * 1024)
    allowed_hosts = [h.strip() for h in os.environ.get("APP_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]
    origin = os.environ.get("ALLOWED_ORIGIN", "").strip()
    if origin == "*":
        raise RuntimeConfigurationError("ALLOWED_ORIGIN must be an exact trusted origin")

    @asynccontextmanager
    async def lifespan(app):
        if runtime_name() != "local":
            raise RuntimeConfigurationError("The portable HTTP server requires APP_RUNTIME=local")
        password_hash = get_password_hash()
        try:
            if not password_hash:
                raise ValueError("Missing authentication configuration")
            bcrypt.checkpw(b"configuration-check", password_hash.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeConfigurationError("Set ACCESS_PASSWORD_HASH_FILE to a valid bcrypt hash") from exc
        from inference import validate_configuration
        validate_configuration()
        app.state.runtime = get_runtime()
        app.state.static_assets = _static_asset_manifest()
        app.state.inflight = asyncio.Semaphore(8)
        app.state.uploads = asyncio.Semaphore(2)
        if start_worker:
            app.state.runtime.start()
        try:
            yield
        finally:
            if start_worker:
                await run_in_threadpool(app.state.runtime.stop)

    app = FastAPI(title="Public Comment Analyzer", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    if origin:
        app.add_middleware(CORSMiddleware, allow_origins=[origin],
                           allow_methods=["GET", "POST", "OPTIONS"],
                           allow_headers=["Content-Type", "X-Access-Key"])

    @app.middleware("http")
    async def response_security(request, call_next):
        if request.url.path.startswith('/api/'):
            # Admission occurs before reading the body or doing bcrypt work.
            # Two upload buffers are the maximum, including chunked requests.
            if app.state.inflight.locked():
                response = error_response('SERVER_BUSY', 'The server is busy. Please retry shortly.', 503)
            else:
                async with app.state.inflight:
                    if request.url.path == '/api/upload':
                        if app.state.uploads.locked():
                            response = error_response('SERVER_BUSY', 'Uploads are busy. Please retry shortly.', 503)
                        else:
                            async with app.state.uploads:
                                response = await call_next(request)
                    else:
                        response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com"
        )
        if request.url.scheme == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    @app.get("/api/health")
    async def health():
        if start_worker and not app.state.runtime.healthy():
            return error_response('WORKER_UNAVAILABLE', 'Background processing is unavailable', 503)
        return {"status": "ok"}

    @app.get("/api/config")
    async def public_config():
        return {"demoMode": os.environ.get("LLM_PROVIDER", "").strip() == "demo"}

    @app.get("/api/download")
    async def download(key: str, expires: int, signature: str):
        try:
            path = app.state.runtime.objects.verify_download(key, expires, signature)
        except StorageError:
            return error_response("INVALID_DOWNLOAD", "Download link is invalid or expired", 403)
        media_type = "text/csv" if path.suffix == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return FileResponse(path, media_type=media_type, filename="analysis-results" + path.suffix)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def dispatch(path: str, request: Request):
        method = request.method
        routes = {("POST", "auth/validate"): "auth_handler", ("POST", "upload"): "upload_handler", ("POST", "process"): "row_processor"}
        name = routes.get((method, path))
        job_id = None
        match = _JOB_ROUTE.fullmatch(path)
        if match:
            kind, job_id, suffix = match.groups()
            if kind == "process" and suffix == "/preview-confirm" and method == "POST":
                name = "row_processor"
            elif kind == 'process' and suffix == '/cancel' and method == 'POST':
                name = 'cancel'
            elif suffix is None:
                name = {("GET", "status"): "status_handler", ("GET", "results"): "aggregate_analyzer",
                        ("POST", "dashboard"): "dashboard_generator"}.get((method, kind))
        if not name:
            return error_response("NOT_FOUND", "Endpoint not found", 404)
        peer = request.client.host if request.client else "unknown"
        if not limiter.allow("requests:" + peer, max_requests):
            return error_response("RATE_LIMITED", "Too many requests. Please retry shortly.", 429)
        if name == "auth_handler" and not limiter.allow("auth:" + peer, 12):
            return error_response("RATE_LIMITED", "Too many sign-in attempts. Please retry shortly.", 429)
        event = {"httpMethod": method, "path": request.url.path,
                 "headers": dict(request.headers), "pathParameters": {"jobId": job_id} if job_id else {},
                 "isBase64Encoded": name == "upload_handler"}
        if name != "auth_handler" and not await run_in_threadpool(validate_access_key, event):
            return error_response("UNAUTHORIZED", "Invalid or missing access key", 401)
        if name in {"row_processor", "dashboard_generator", "upload_handler"}:
            if not limiter.allow("expensive:global", max_expensive):
                return error_response("RATE_LIMITED", "Too many submissions. Please retry shortly.", 429)
        limit = max_body if name == "upload_handler" else 1024 * 1024
        if name == "auth_handler":
            limit = 1024
        body = bytearray()
        try:
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    return error_response("REQUEST_TOO_LARGE", "Request exceeds the configured size limit", 413)
                body.extend(chunk)
            if name == "upload_handler":
                event["body"] = base64.b64encode(body).decode("ascii")
            else:
                event["body"] = body.decode("utf-8") if body else "{}"
                if method == "POST":
                    parsed = json.loads(event["body"])
                    if not isinstance(parsed, dict):
                        raise ValueError("JSON body must be an object")
                    if any(key in parsed for key in ("asyncProcessing", "asyncAnalysis", "pathParameters", "inputKey", "outputKey")):
                        raise ValueError("Internal task fields are not accepted by the HTTP API")
                    if name == "row_processor" and not job_id:
                        _validate_process_body(parsed)
                    if name == "dashboard_generator" and not isinstance(parsed.get("prompt"), str):
                        raise ValueError("Dashboard prompt must be text")
        except (UnicodeError, ValueError, TypeError):
            return error_response("INVALID_REQUEST", "Request body is invalid", 400)
        try:
            if name == 'cancel':
                if not app.state.runtime.jobs.get(job_id):
                    return error_response('JOB_NOT_FOUND', 'Job not found', 404)
                if not app.state.runtime.jobs.cancel(job_id):
                    return error_response('INVALID_JOB_STATE', 'Only queued jobs and previews waiting for confirmation can be cancelled.', 409)
                return JSONResponse({'jobId': job_id, 'status': 'failed'})
            handler = importlib.import_module(f"backend.{name}.handler")
            result = await run_in_threadpool(handler.lambda_handler, event, SimpleNamespace(function_name=name, request_id="local"))
            headers = {k: v for k, v in result.get("headers", {}).items()
                       if not k.lower().startswith("access-control-")}
            return Response(content=result.get("body", ""), status_code=result.get("statusCode", 500),
                            headers=headers, media_type="application/json")
        except Exception:
            return error_response("INTERNAL_ERROR", "The request could not be completed", 500)

    @app.get("/{path:path}")
    async def frontend(path: str):
        parts = path.split('/')
        if '\\' in path or '\x00' in path or any(part.startswith('.') for part in parts):
            return error_response("NOT_FOUND", "File not found", 404)
        candidate = app.state.static_assets.get(path)
        if candidate is not None:
            return FileResponse(candidate, headers={'Cache-Control': 'no-cache'} if path == 'index.html' else None)
        index = app.state.static_assets.get('index.html')
        if '.' not in parts[-1] and index is not None:
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return error_response("NOT_FOUND", "Build the frontend or use its development server", 404)

    return app


app = create_app()
