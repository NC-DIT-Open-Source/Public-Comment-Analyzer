"""Shared authentication module for Lambda handlers."""

import os
import json
import threading
import bcrypt
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lock-guarded lazy init: validate_access_key is reached from threaded handler
# code. Every read AND write of these globals happens under the lock — no
# unsynchronized fast-path read (Checkmarx Race Condition Global Scope flags
# double-checked locking). The lock is non-reentrant: _get_password_hash must
# release it before calling _get_secrets_client.
_init_lock = threading.Lock()
_secrets_client = None
_cached_password_hash = None


def _get_secrets_client():
    global _secrets_client
    with _init_lock:
        if _secrets_client is None:
            _secrets_client = boto3.client('secretsmanager')
        return _secrets_client


def _get_password_hash() -> str:
    """Retrieve the access password hash from Secrets Manager (cached per Lambda instance).

    The stored value is a bcrypt hash string (e.g. "$2b$12$...").
    """
    global _cached_password_hash
    with _init_lock:
        if _cached_password_hash is not None:
            return _cached_password_hash

    secret_name = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')
    if not secret_name:
        return ''

    try:
        response = _get_secrets_client().get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        fetched = secret.get('password_hash', '')
        with _init_lock:
            _cached_password_hash = fetched
        return fetched
    except ClientError as e:
        logger.error(f"Failed to retrieve access password secret: {e}")
        return ''


def _verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time bcrypt verification. Returns False on any malformed input."""
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except (ValueError, TypeError):
        # Hash isn't a valid bcrypt string — fail closed.
        return False


def validate_access_key(event: dict) -> bool:
    """
    Validate the X-Access-Key header against the stored bcrypt password hash.

    Returns True if valid, False otherwise. Fails closed: if no secret is
    configured and no LOCAL_PASSWORD_HASH is set, all requests are rejected.
    """
    headers = event.get('headers', {}) or {}
    # API Gateway lowercases header names
    access_key = headers.get('x-access-key') or headers.get('X-Access-Key') or ''
    if not access_key:
        return False

    # Local-dev path: a bcrypt hash is provided directly via env var.
    local_hash = os.environ.get('LOCAL_PASSWORD_HASH', '')
    if local_hash:
        return _verify_password(access_key, local_hash)

    secret_name = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')
    if not secret_name:
        logger.warning("Auth not configured: no ACCESS_PASSWORD_SECRET_NAME or LOCAL_PASSWORD_HASH set")
        return False

    return _verify_password(access_key, _get_password_hash())


def build_unauthorized_response(cors_origin: str) -> dict:
    """Return a standard 401 response."""
    return {
        'statusCode': 401,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': cors_origin,
        },
        'body': json.dumps({
            'error': {
                'code': 'UNAUTHORIZED',
                'message': 'Invalid or missing access key'
            }
        })
    }


def clear_cache():
    """Clear the cached password hash (useful for testing or secret rotation)."""
    global _cached_password_hash
    with _init_lock:
        _cached_password_hash = None
