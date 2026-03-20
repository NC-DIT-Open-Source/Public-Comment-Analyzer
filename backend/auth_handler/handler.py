"""Lambda handler for access password validation."""

import json
import os
import hashlib
import boto3
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CORS_ORIGIN = os.environ.get('ALLOWED_ORIGIN') or '*'
if CORS_ORIGIN == '*':
    logger.warning("ALLOWED_ORIGIN not set, falling back to '*'")
SECRET_NAME = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')

_secrets_client = None
_cached_hash = None


def _get_secrets_client():
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client('secretsmanager')
    return _secrets_client


def _get_password_hash():
    global _cached_hash
    if _cached_hash is not None:
        return _cached_hash
    # Allow a direct hash for local development (no Secrets Manager needed)
    local_hash = os.environ.get('LOCAL_PASSWORD_HASH', '')
    if local_hash:
        _cached_hash = local_hash
        return _cached_hash
    if not SECRET_NAME:
        return ''
    try:
        resp = _get_secrets_client().get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(resp['SecretString'])
        _cached_hash = secret.get('password_hash', '')
        return _cached_hash
    except Exception as e:
        logger.error(f"Error retrieving secret: {e}")
        return ''


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
        input_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        stored_hash = _get_password_hash()
        if not stored_hash:
            return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Auth not configured'})}
        if input_hash == stored_hash:
            return {'statusCode': 200, 'headers': headers, 'body': json.dumps({'valid': True})}
        else:
            return {'statusCode': 401, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Invalid password'})}
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'valid': False, 'message': 'Internal error'})}
