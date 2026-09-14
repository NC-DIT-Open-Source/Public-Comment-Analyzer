"""Provider-neutral persistence, background work, and authentication boundaries."""

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Protocol


class RuntimeConfigurationError(RuntimeError):
    """The operator must correct configuration before serving requests."""


class StorageError(RuntimeError):
    """A safe, provider-independent persistence or queue failure."""

    def __init__(self, code: str, message: str = "Persistence operation failed"):
        self.code = code
        # Keep legacy error response handling compatible during adapter migration.
        self.response = {"Error": {"Code": code, "Message": message}}
        super().__init__(message)


class ObjectStore(Protocol):
    def download(self, key: str, path: str) -> None: ...
    def upload(self, path: str, key: str) -> None: ...
    def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> None: ...
    def exists(self, key: str) -> bool: ...
    def signed_url(self, key: str, expires: int = 3600) -> str: ...


class JobStore(Protocol):
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def put(self, item: dict[str, Any]) -> None: ...
    def update(self, job_id: str, fields: dict[str, Any]) -> None: ...
    def claim_preview(self, job_id: str) -> bool: ...


class TaskRuntime(Protocol):
    objects: ObjectStore
    jobs: JobStore
    def enqueue(self, name: str, payload: dict[str, Any]) -> None: ...


def runtime_name() -> str:
    name = os.environ.get("APP_RUNTIME", "local").strip().lower() or 'local'
    if name != 'local':
        raise RuntimeConfigurationError("This edition supports APP_RUNTIME=local on any container host")
    return name


def positive_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeConfigurationError(f"{name} must be an integer") from exc
    if not 1 <= value <= maximum:
        raise RuntimeConfigurationError(f"{name} must be between 1 and {maximum}")
    return value


@lru_cache(maxsize=8)
def _local_runtime(directory: str):
    if __package__:
        from .adapters.local import LocalRuntime
    else:
        from adapters.local import LocalRuntime
    return LocalRuntime(Path(directory))


def get_runtime():
    runtime_name()
    directory = str(Path(os.environ.get("APP_DATA_DIR", ".data")).expanduser().resolve())
    return _local_runtime(directory)


def get_object_store() -> ObjectStore:
    return get_runtime().objects


def get_job_store() -> JobStore:
    return get_runtime().jobs


def enqueue_task(name: str, payload: dict[str, Any]) -> None:
    if name not in {"row_processor", "aggregate_analyzer"}:
        raise StorageError("INVALID_TASK", "Unknown background task")
    get_runtime().enqueue(name, payload)


def get_password_hash() -> str:
    """Read mounted bcrypt secrets without ever returning plaintext credentials."""
    secret_file = os.environ.get("ACCESS_PASSWORD_HASH_FILE", "")
    if secret_file:
        try:
            path = Path(secret_file)
            if path.stat().st_size > 1024:
                return ""
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return ""
    direct = os.environ.get("LOCAL_PASSWORD_HASH", "")
    if direct:
        return direct
    return ""
