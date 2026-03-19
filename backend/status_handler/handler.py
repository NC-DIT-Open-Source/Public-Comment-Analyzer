"""Lambda handler for job status checking."""

import json
import re
import hashlib
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['JOBS_TABLE'])
CORS_ORIGIN = os.environ.get('ALLOWED_ORIGIN') or '*'
SECRET_NAME = os.environ.get('ACCESS_PASSWORD_SECRET_NAME', '')

UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

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
    if not SECRET_NAME:
        return ''
    try:
        resp = _get_secrets_client().get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(resp['SecretString'])
        _cached_hash = secret.get('password_hash', '')
        return _cached_hash
    except Exception as e:
        print(f"ERROR retrieving secret: {e}")
        return ''


def _check_auth(event):
    if not SECRET_NAME:
        return True
    headers = event.get('headers', {}) or {}
    access_key = headers.get('x-access-key') or headers.get('X-Access-Key') or ''
    if not access_key:
        return False
    stored_hash = _get_password_hash()
    if not stored_hash:
        return False
    return hashlib.sha256(access_key.encode('utf-8')).hexdigest() == stored_hash


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def lambda_handler(event, context):
    if not _check_auth(event):
        return {
            'statusCode': 401,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps({'error': {'code': 'UNAUTHORIZED', 'message': 'Invalid or missing access key'}})
        }

    job_id = event['pathParameters']['jobId']

    if not UUID_PATTERN.match(job_id):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps({'error': {'code': 'INVALID_JOB_ID', 'message': 'jobId must be a valid UUID'}})
        }

    try:
        response = table.get_item(Key={'jobId': job_id})
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
                'body': json.dumps({'error': {'code': 'JOB_NOT_FOUND', 'message': 'Job not found'}})
            }
        item = response['Item']
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps({
                'jobId': item.get('jobId'),
                'status': item.get('status'),
                'progress': round((item.get('completedRows', 0) / item.get('totalRows', 1)) * 100, 2) if item.get('totalRows') else 0,
                'completedRows': item.get('completedRows', 0),
                'totalRows': item.get('totalRows', 0),
                'errors': item.get('errors', [])
            }, default=decimal_default)
        }
    except Exception as e:
        print(f"Status handler error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps({'error': {'code': 'INTERNAL_ERROR', 'message': 'An internal error occurred'}})
        }
