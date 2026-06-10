"""Lambda handler for access password validation."""

import json
import os
import threading
import bcrypt
import boto3
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CORS_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '')
if not CORS_ORIGIN:
    logger.error("ALLOWED_ORIGIN is not set; CORS will fail closed")
SECRET_NAME = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')

# Lock-guarded lazy init so concurrent requests on a warm container can't
# observe partially-initialized globals. Every read AND write of these globals
# happens under the lock — no unsynchronized fast-path read (Checkmarx Race
# Condition Global Scope flags double-checked locking).
_init_lock = threading.Lock()
_secrets_client = None
_cached_hash = None


def _get_secrets_client():
    global _secrets_client
    with _init_lock:
        if _secrets_client is None:
            _secrets_client = boto3.client('secretsmanager')
        return _secrets_client


def _get_password_hash():
    """Return the stored bcrypt hash (cached). Empty string means auth not configured."""
    global _cached_hash
    with _init_lock:
        if _cached_hash is not None:
            return _cached_hash
    # Allow a direct hash for local development (no Secrets Manager needed)
    local_hash = os.environ.get('LOCAL_PASSWORD_HASH', '')
    if local_hash:
        with _init_lock:
            _cached_hash = local_hash
        return local_hash
    if not SECRET_NAME:
        return ''
    try:
        resp = _get_secrets_client().get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(resp['SecretString'])
        fetched = secret.get('password_hash', '')
        with _init_lock:
            _cached_hash = fetched
        return fetched
    except Exception as e:
        logger.error(f"Error retrieving secret: {e}")
        return ''


def _verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time bcrypt verification. Fails closed on any malformed input."""
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def lambda_handler(event, context):
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': CORS_ORIGIN,
        'Access-Control-Allow-Headers': 'Content-Type,X-Access-Key'
    }
    try:
        body = json.loads(event.get('body', '{}') or '{}')
        password = body.get('password', '')
        if not password:
            return {'statusCode': 401, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Password is required'})}
        stored_hash = _get_password_hash()
        if not stored_hash:
            return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Auth not configured'})}
        if _verify_password(password, stored_hash):
            return {'statusCode': 200, 'headers': headers, 'body': json.dumps({'valid': True})}
        else:
            return {'statusCode': 401, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Invalid password'})}
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Internal error'})}
