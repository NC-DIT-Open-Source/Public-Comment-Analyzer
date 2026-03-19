"""Shared authentication module for Lambda handlers."""

import os
import json
import hashlib
import boto3
from botocore.exceptions import ClientError

_secrets_client = None
_cached_password_hash = None


def _get_secrets_client():
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client('secretsmanager')
    return _secrets_client


def _get_password_hash() -> str:
    """Retrieve the access password hash from Secrets Manager (cached per Lambda instance)."""
    global _cached_password_hash
    if _cached_password_hash is not None:
        return _cached_password_hash

    secret_name = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')
    if not secret_name:
        return ''

    try:
        response = _get_secrets_client().get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        _cached_password_hash = secret.get('password_hash', '')
        return _cached_password_hash
    except ClientError as e:
        print(f"ERROR: Failed to retrieve access password secret: {e}")
        return ''


def _hash_password(password: str) -> str:
    """Hash a password with SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def validate_access_key(event: dict) -> bool:
    """
    Validate the X-Access-Key header against the stored password hash.

    Returns True if valid, False otherwise.
    """
    secret_name = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')
    if not secret_name:
        # No secret configured — skip auth (e.g. local dev)
        return True

    headers = event.get('headers', {}) or {}
    # API Gateway lowercases header names
    access_key = headers.get('x-access-key') or headers.get('X-Access-Key') or ''

    if not access_key:
        return False

    stored_hash = _get_password_hash()
    if not stored_hash:
        return False

    return _hash_password(access_key) == stored_hash


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
    _cached_password_hash = None
