"""Unit tests for status handler Lambda."""

import json
import os
import sys
import unittest
import uuid
from unittest.mock import MagicMock, patch

os.environ['JOBS_TABLE'] = 'test-jobs-table'
os.environ['ALLOWED_ORIGIN'] = '*'

# Auth shim is loaded from sys.path side-load; bypass auth for tests.
sys.path.insert(0, os.path.dirname(__file__))


def _build_event(job_id):
    return {
        'pathParameters': {'jobId': job_id},
        'headers': {'X-Access-Key': 'irrelevant-bypassed'},
    }


class TestStatusHandler(unittest.TestCase):

    def setUp(self):
        # Re-import handler under fresh patch so we can swap out the table object.
        import importlib
        if 'handler' in sys.modules:
            del sys.modules['handler']
        with patch('boto3.resource'):
            import handler  # type: ignore
            self.handler = handler

    def _patch_auth_to_pass(self):
        return patch.object(self.handler, 'validate_access_key', return_value=True)

    def test_returns_400_for_invalid_uuid(self):
        with self._patch_auth_to_pass():
            response = self.handler.lambda_handler(_build_event('not-a-uuid'), None)
        self.assertEqual(response['statusCode'], 400)

    def test_includes_preview_rows_when_status_is_preview_ready(self):
        job_id = str(uuid.uuid4())
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': job_id,
                'status': 'preview_ready',
                'completedRows': 20,
                'totalRows': 100,
                'errors': [],
                'previewRows': [
                    {'comment': 'I support legalization', 'support': 'Support', '_error': ''},
                    {'comment': 'Cannabis should remain illegal', 'support': 'Oppose', '_error': ''}
                ]
            }
        }
        self.handler.table = mock_table

        with self._patch_auth_to_pass():
            response = self.handler.lambda_handler(_build_event(job_id), None)

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['status'], 'preview_ready')
        self.assertIn('previewRows', body)
        self.assertEqual(len(body['previewRows']), 2)
        self.assertEqual(body['previewRows'][0]['support'], 'Support')

    def test_omits_preview_rows_when_status_is_completed(self):
        job_id = str(uuid.uuid4())
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': job_id,
                'status': 'completed',
                'completedRows': 100,
                'totalRows': 100,
                'errors': []
            }
        }
        self.handler.table = mock_table

        with self._patch_auth_to_pass():
            response = self.handler.lambda_handler(_build_event(job_id), None)

        body = json.loads(response['body'])
        self.assertNotIn('previewRows', body)


if __name__ == '__main__':
    unittest.main()
