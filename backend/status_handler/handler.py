"""Lambda handler for job status checking."""

import json
import re
import os
import logging
from decimal import Decimal

import boto3

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from auth import validate_access_key, build_unauthorized_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['JOBS_TABLE'])
CORS_ORIGIN = os.environ.get('ALLOWED_ORIGIN') or '*'

UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def lambda_handler(event, context):
    if not validate_access_key(event):
        return build_unauthorized_response(CORS_ORIGIN)

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
        body = {
            'jobId': item.get('jobId'),
            'status': item.get('status'),
            'progress': round((item.get('completedRows', 0) / item.get('totalRows', 1)) * 100, 2) if item.get('totalRows') else 0,
            'completedRows': item.get('completedRows', 0),
            'totalRows': item.get('totalRows', 0),
            'errors': item.get('errors', [])
        }
        # Surface preview rows + the analysis column definitions so the frontend
        # can render the preview table while gating on user confirmation.
        if item.get('status') == 'preview_ready' and item.get('previewRows'):
            body['previewRows'] = item['previewRows']
            body['analysisColumns'] = item.get('analysisColumns', [])
            body['selectedCommentColumn'] = item.get('selectedCommentColumn')
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps(body, default=decimal_default)
        }
    except Exception as e:
        logger.error(f"Status handler error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': CORS_ORIGIN},
            'body': json.dumps({'error': {'code': 'INTERNAL_ERROR', 'message': 'An internal error occurred'}})
        }
