"""Unit tests for provider-neutral row processing and API compatibility."""

import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch, MagicMock
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from handler import (
    lambda_handler,
    _determine_file_type,
    _update_job_status,
    _process_single_row,
    _should_use_preview,
    PREVIEW_ROW_COUNT,
    PREVIEW_MIN_FILE_SIZE
)

from inference import InferenceError

class TestRowProcessorHandler(unittest.TestCase):
    """Test cases for row processor handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'
    
    def test_missing_file_id(self):
        """Test that missing fileId returns 400 error."""
        event = {
            'body': json.dumps({
                'analysisColumns': [
                    {'name': 'category', 'instructions': 'Categorize the comment'}
                ]
            })
        }
        
        response = lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'MISSING_FILE_ID')
    
    def test_missing_analysis_columns(self):
        """Test that missing analysisColumns returns 400 error."""
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4())  # Valid UUID
            })
        }
        
        response = lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'MISSING_ANALYSIS_COLUMNS')
    
    def test_invalid_analysis_column_missing_name(self):
        """Test that analysis column without name returns 400 error."""
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),  # Valid UUID
                'analysisColumns': [
                    {'instructions': 'Categorize the comment'}
                ]
            })
        }
        
        response = lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'INVALID_ANALYSIS_COLUMN')
    
    def test_invalid_analysis_column_missing_instructions(self):
        """Test that analysis column without instructions returns 400 error."""
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),  # Valid UUID
                'analysisColumns': [
                    {'name': 'category'}
                ]
            })
        }
        
        response = lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'INVALID_ANALYSIS_COLUMN')
    
    @patch('handler.invoke_text', return_value='{"category":"pro","rating":"6"}')
    def test_process_single_row_success(self, invoke):
        result = _process_single_row({'comment': 'This is a test comment'}, [
            {'name': 'category', 'instructions': 'Categorize as pro or against'},
            {'name': 'rating', 'instructions': 'Rate 1-7'}])
        self.assertEqual(result, {'category': 'pro', 'rating': '6'})
        invoke.assert_called_once()
        self.assertEqual(invoke.call_args.kwargs['role'], 'row')
    
    @patch('handler.time.sleep')
    @patch('handler.invoke_text')
    def test_process_single_row_retry_on_failure(self, invoke, sleep):
        invoke.side_effect = [InferenceError('temporary'), InferenceError('temporary'), '{"category":"pro"}']
        result = _process_single_row({'comment': 'Test'}, [{'name': 'category', 'instructions': 'Categorize'}])
        self.assertEqual(result['category'], 'pro')
        self.assertEqual(invoke.call_count, 3)
    
    @patch('handler.time.sleep')
    @patch('handler.invoke_text', side_effect=InferenceError('temporary'))
    def test_process_single_row_max_retries_exceeded(self, invoke, sleep):
        with self.assertRaises(InferenceError):
            _process_single_row({'comment': 'Test'}, [{'name': 'category', 'instructions': 'Categorize'}])
        self.assertEqual(invoke.call_count, 3)
    
    @patch('handler.invoke_text', return_value='{"support":"Support"}')
    def test_categorized_column_uses_temperature_zero(self, invoke):
        _process_single_row({'comment': 'Support'}, self._category_columns())
        self.assertEqual(invoke.call_args.kwargs['temperature'], 0)

    @patch('handler.invoke_text', return_value='{"summary":"A summary."}')
    def test_open_text_only_does_not_force_temperature(self, invoke):
        _process_single_row({'comment': 'Test'}, [{'name': 'summary', 'instructions': 'One sentence'}])
        self.assertIsNone(invoke.call_args.kwargs['temperature'])

    @patch('handler.invoke_text', side_effect=['{"support":"banana"}', 'Support'])
    def test_retry_call_uses_temperature_zero(self, invoke):
        result = _process_single_row({'comment': 'Support'}, self._category_columns())
        self.assertEqual(result['support'], 'Support')
        self.assertEqual(invoke.call_count, 2)
        for call in invoke.call_args_list:
            self.assertEqual(call.kwargs['temperature'], 0)

    @patch('handler.invoke_text', return_value='{"support":"Support"}')
    def test_examples_are_rendered_into_prompt(self, invoke):
        columns = self._category_columns()
        columns[0]['examples'] = [{'commentText': 'Legalize cannabis now!', 'label': 'Support'},
                                  {'commentText': 'Cannabis should remain illegal.', 'label': 'Oppose'}]
        _process_single_row({'comment': 'Support'}, columns)
        prompt = invoke.call_args.args[0]
        self.assertIn('Legalize cannabis now!', prompt)
        self.assertIn('Cannabis should remain illegal.', prompt)
        self.assertIn('Support', prompt)
        self.assertIn('Oppose', prompt)
        self.assertIn('<analysis_criteria>', prompt)

    @patch('handler.invoke_text', return_value='{"support":"Support"}')
    def test_no_examples_omits_examples_block(self, invoke):
        _process_single_row({'comment': 'Support'}, self._category_columns())
        self.assertNotIn('&quot;examples&quot;', invoke.call_args.args[0])

    def test_invalid_example_missing_label_returns_400(self):
        """An example missing a label is rejected at the API layer."""
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),
                'selectedCommentColumn': 'comment',
                'contextDescription': 'Test context',
                'analysisColumns': [{
                    'name': 'support',
                    'type': 'categorized',
                    'options': [
                        {'value': 'Support', 'description': 'In favor'},
                        {'value': 'Oppose', 'description': 'Against'}
                    ],
                    'examples': [
                        {'commentText': 'A comment without a label'}
                    ]
                }]
            })
        }
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'INVALID_EXAMPLE')

    def test_too_many_examples_returns_400(self):
        """More than 14 examples per column is rejected."""
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),
                'selectedCommentColumn': 'comment',
                'contextDescription': 'Test context',
                'analysisColumns': [{
                    'name': 'support',
                    'type': 'categorized',
                    'options': [
                        {'value': 'Support', 'description': 'In favor'},
                        {'value': 'Oppose', 'description': 'Against'}
                    ],
                    'examples': [
                        {'commentText': f'Example {i}', 'label': 'Support'} for i in range(15)
                    ]
                }]
            })
        }
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'TOO_MANY_EXAMPLES')

    @patch('handler.invoke_text', return_value='{"col1":"val1","col2":"val2","col3":"val3"}')
    def test_prompt_includes_all_columns(self, invoke):
        columns = [{'name': f'col{i}', 'instructions': f'Instruction {i}'} for i in range(1, 4)]
        _process_single_row({'comment': 'Test'}, columns)
        for i in range(1, 4):
            self.assertIn(f'Instruction {i}', invoke.call_args.args[0])

    @staticmethod
    def _category_columns():
        return [{'name': 'support', 'type': 'categorized', 'options': [
            {'value': 'Support', 'description': 'In favor'}, {'value': 'Oppose', 'description': 'Against'}]}]


class TestInitialProcessRoutesToPreview(unittest.TestCase):
    """The initial POST /process call should kick off the preview phase when applicable."""

    def setUp(self):
        self.file_type_patch = patch('handler._determine_file_type', return_value='csv')
        self.file_type_patch.start()
        self.addCleanup(self.file_type_patch.stop)
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'

    @patch('handler.enqueue_task')
    @patch('handler._create_job_record_quick')
    @patch('handler._get_row_count')
    def test_initial_process_uses_preview_phase_for_categorized_large_file(
        self, mock_row_count, mock_create_record, mock_boto_client
    ):
        mock_row_count.return_value = 200  # large enough for preview
        mock_lambda = MagicMock()
        mock_boto_client.return_value = mock_lambda

        ctx = MagicMock()
        ctx.function_name = 'PublicCommentAnalyzer-RowProcessor-test'
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),
                'selectedCommentColumn': 'comment',
                'contextDescription': 'Test context',
                'analysisColumns': [{
                    'name': 'support',
                    'type': 'categorized',
                    'options': [
                        {'value': 'Support', 'description': 'In favor'},
                        {'value': 'Oppose', 'description': 'Against'}
                    ]
                }]
            })
        }
        response = lambda_handler(event, ctx)
        self.assertEqual(response['statusCode'], 200)

        invoke_payload = mock_boto_client.call_args.args[1]
        self.assertEqual(invoke_payload.get('phase'), 'preview')

    @patch('handler.enqueue_task')
    @patch('handler._create_job_record_quick')
    @patch('handler._get_row_count')
    def test_initial_process_uses_full_phase_for_open_text_only(
        self, mock_row_count, mock_create_record, mock_boto_client
    ):
        mock_row_count.return_value = 1000
        mock_lambda = MagicMock()
        mock_boto_client.return_value = mock_lambda

        ctx = MagicMock()
        ctx.function_name = 'PublicCommentAnalyzer-RowProcessor-test'
        event = {
            'body': json.dumps({
                'fileId': str(uuid.uuid4()),
                'selectedCommentColumn': 'comment',
                'contextDescription': 'Test context',
                'analysisColumns': [{
                    'name': 'summary',
                    'type': 'open_text',
                    'instructions': 'Summarize.'
                }]
            })
        }
        response = lambda_handler(event, ctx)
        self.assertEqual(response['statusCode'], 200)

        invoke_payload = mock_boto_client.call_args.args[1]
        self.assertEqual(invoke_payload.get('phase'), 'full')


class TestPreviewDecision(unittest.TestCase):
    """The decision rule for whether to run the preview phase."""

    def _categorized_col(self):
        return {
            'name': 'support',
            'type': 'categorized',
            'options': [
                {'value': 'Support', 'description': 'In favor'},
                {'value': 'Oppose', 'description': 'Against'}
            ]
        }

    def _open_col(self):
        return {'name': 'summary', 'type': 'open_text', 'instructions': 'Summarize.'}

    def test_preview_when_categorized_and_file_is_large_enough(self):
        self.assertTrue(_should_use_preview([self._categorized_col()], total_rows=100))

    def test_no_preview_when_no_categorized_columns(self):
        self.assertFalse(_should_use_preview([self._open_col()], total_rows=1000))

    def test_no_preview_when_file_smaller_than_threshold(self):
        # If the user's file is already smaller than PREVIEW_MIN_FILE_SIZE, the preview
        # would re-process most of the file anyway — just run it normally.
        self.assertFalse(
            _should_use_preview([self._categorized_col()], total_rows=PREVIEW_MIN_FILE_SIZE - 1)
        )

    def test_preview_at_threshold_boundary(self):
        self.assertTrue(
            _should_use_preview([self._categorized_col()], total_rows=PREVIEW_MIN_FILE_SIZE)
        )


class TestPreviewConfirmEndpoint(unittest.TestCase):
    """API contract for POST /process/{jobId}/preview-confirm."""

    def setUp(self):
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'

    def _build_event(self, job_id):
        return {
            'pathParameters': {'jobId': job_id},
            'httpMethod': 'POST',
            'resource': '/process/{jobId}/preview-confirm',
            'body': None
        }

    def test_returns_400_when_path_jobid_is_invalid(self):
        event = self._build_event('not-a-uuid')
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 400)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'INVALID_FILE_ID')

    @patch('handler.get_job_store')
    def test_returns_404_when_job_does_not_exist(self, mock_dynamo):
        # DynamoDB returns no Item
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_table.get.return_value = mock_table.get_item.return_value.get('Item')
        mock_dynamo.return_value = mock_table

        event = self._build_event(str(uuid.uuid4()))
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 404)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'JOB_NOT_FOUND')

    @patch('handler.get_job_store')
    def test_returns_409_when_job_is_not_in_preview_ready_state(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'jobId': 'abc', 'status': 'completed'}
        }
        mock_table.get.return_value = mock_table.get_item.return_value.get('Item')
        mock_dynamo.return_value = mock_table

        event = self._build_event(str(uuid.uuid4()))
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 409)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'INVALID_JOB_STATE')

    @patch('handler.enqueue_task')
    @patch('handler.get_job_store')
    def test_invokes_row_processor_async_with_confirm_phase(self, mock_dynamo, mock_boto_client):
        job_id = str(uuid.uuid4())
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': job_id,
                'status': 'preview_ready',
                'fileId': 'fid',
                'fileType': 'csv',
                'inputFileKey': f'uploads/fid/input.csv',
                'outputFileKey': f'results/{job_id}/output.csv',
                'analysisColumns': [{'name': 'support', 'type': 'categorized',
                                     'options': [{'value': 'Support', 'description': 'In favor'},
                                                 {'value': 'Oppose', 'description': 'Against'}]}],
                'selectedCommentColumn': 'comment',
                'contextDescription': 'Test context'
            }
        }
        mock_table.get.return_value = mock_table.get_item.return_value.get('Item')
        mock_dynamo.return_value = mock_table
        mock_lambda = MagicMock()
        mock_boto_client.return_value = mock_lambda

        ctx = MagicMock()
        ctx.function_name = 'PublicCommentAnalyzer-RowProcessor-test'
        event = self._build_event(job_id)
        response = lambda_handler(event, ctx)

        self.assertEqual(response['statusCode'], 200)
        # Must have invoked self async with phase=confirm
        invoke_call = mock_boto_client.call_args
        self.assertEqual(invoke_call.args[0], 'row_processor')
        payload = invoke_call.args[1]
        self.assertTrue(payload.get('asyncProcessing'))
        self.assertEqual(payload.get('phase'), 'confirm')
        self.assertEqual(payload.get('jobId'), job_id)


if __name__ == '__main__':
    unittest.main()
