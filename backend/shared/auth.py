"""Shared bcrypt authentication; credentials stay out of browser storage."""

import json
import bcrypt
from runtime import get_password_hash


def _get_password_hash() -> str:
    return get_password_hash()


def _verify_password(password: str, stored_hash: str) -> bool:
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False
    if not password or not stored_hash:
        return False
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > 72:
            return False
        return bcrypt.checkpw(encoded, stored_hash.encode("utf-8"))
    except (ValueError, TypeError, UnicodeError):
        return False


def validate_access_key(event: dict) -> bool:
    headers = event.get("headers") or {}
    access_key = headers.get("x-access-key") or headers.get("X-Access-Key") or ""
    return _verify_password(access_key, _get_password_hash())


def build_unauthorized_response(cors_origin: str) -> dict:
    return {"statusCode": 401, "headers": {
        "Content-Type": "application/json", "Access-Control-Allow-Origin": cors_origin,
    }, "body": json.dumps({"error": {
        "code": "UNAUTHORIZED", "message": "Invalid or missing access key",
    }})}


def clear_cache():
    """Compatibility hook; mounted authentication secrets are read on each request."""
