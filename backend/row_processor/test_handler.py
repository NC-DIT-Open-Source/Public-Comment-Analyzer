"""Unit tests for row processor Lambda handler."""

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
    
    @patch('handler._get_bedrock_runtime')
    def test_process_single_row_success(self, mock_get_bedrock):
        """Test successful processing of a single row."""
        # Mock Bedrock client
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        
        # Mock Bedrock response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [
                {
                    'text': json.dumps({
                        'category': 'pro',
                        'rating': '6'
                    })
                }
            ]
        }).encode('utf-8')
        
        mock_bedrock.invoke_model.return_value = mock_response
        
        row = {'comment': 'This is a test comment'}
        analysis_columns = [
            {'name': 'category', 'instructions': 'Categorize as pro or against'},
            {'name': 'rating', 'instructions': 'Rate 1-7'}
        ]
        
        result = _process_single_row(row, analysis_columns)
        
        self.assertEqual(result['category'], 'pro')
        self.assertEqual(result['rating'], '6')
        
        # Verify Bedrock was called
        mock_bedrock.invoke_model.assert_called_once()
        call_args = mock_bedrock.invoke_model.call_args
        # Check for the new cross-region model ID
        self.assertIn('claude-haiku', call_args[1]['modelId'])
    
    @patch('handler._get_bedrock_runtime')
    def test_process_single_row_retry_on_failure(self, mock_get_bedrock):
        """Test that processing retries on failure."""
        # Mock Bedrock client
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        
        # First two calls fail, third succeeds
        mock_bedrock.invoke_model.side_effect = [
            Exception("Temporary error"),
            Exception("Temporary error"),
            {
                'body': MagicMock(
                    read=MagicMock(return_value=json.dumps({
                        'content': [{'text': json.dumps({'category': 'pro'})}]
                    }).encode('utf-8'))
                )
            }
        ]
        
        row = {'comment': 'Test'}
        analysis_columns = [{'name': 'category', 'instructions': 'Categorize'}]
        
        result = _process_single_row(row, analysis_columns)
        
        self.assertEqual(result['category'], 'pro')
        self.assertEqual(mock_bedrock.invoke_model.call_count, 3)
    
    @patch('handler._get_bedrock_runtime')
    def test_process_single_row_max_retries_exceeded(self, mock_get_bedrock):
        """Test that processing fails after max retries."""
        # Mock Bedrock client
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        
        # All calls fail
        mock_bedrock.invoke_model.side_effect = Exception("Persistent error")
        
        row = {'comment': 'Test'}
        analysis_columns = [{'name': 'category', 'instructions': 'Categorize'}]
        
        with self.assertRaises(Exception):
            _process_single_row(row, analysis_columns)
        
        self.assertEqual(mock_bedrock.invoke_model.call_count, 3)
    
    @patch('handler._get_bedrock_runtime')
    def test_categorized_column_uses_temperature_zero(self, mock_get_bedrock):
        """When any categorized column is present, Bedrock is called with temperature=0 for determinism."""
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=MagicMock(return_value=json.dumps({
                'content': [{'text': json.dumps({'support': 'Support'})}]
            }).encode('utf-8')))
        }

        row = {'comment': 'Legalize it'}
        analysis_columns = [{
            'name': 'support',
            'type': 'categorized',
            'options': [
                {'value': 'Support', 'description': 'In favor'},
                {'value': 'Oppose', 'description': 'Against'}
            ]
        }]

        _process_single_row(row, analysis_columns)

        body = json.loads(mock_bedrock.invoke_model.call_args[1]['body'])
        self.assertEqual(body.get('temperature'), 0,
                         f"Expected temperature=0 for categorized columns, got body={body}")

    @patch('handler._get_bedrock_runtime')
    def test_open_text_only_does_not_force_temperature(self, mock_get_bedrock):
        """Open-text-only runs leave temperature unset so Bedrock uses its default."""
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=MagicMock(return_value=json.dumps({
                'content': [{'text': json.dumps({'summary': 'A summary.'})}]
            }).encode('utf-8')))
        }

        row = {'comment': 'Some comment text'}
        analysis_columns = [{'name': 'summary', 'instructions': 'One sentence.'}]

        _process_single_row(row, analysis_columns)

        body = json.loads(mock_bedrock.invoke_model.call_args[1]['body'])
        self.assertNotIn('temperature', body,
                         "Open-text-only runs should not set temperature explicitly")

    @patch('handler._get_bedrock_runtime')
    def test_retry_call_uses_temperature_zero(self, mock_get_bedrock):
        """Categorized retry calls always use temperature=0."""
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock

        # First call returns an unmatched value to trigger retry path; retry returns valid value
        mock_bedrock.invoke_model.side_effect = [
            {
                'body': MagicMock(read=MagicMock(return_value=json.dumps({
                    'content': [{'text': json.dumps({'support': 'banana'})}]
                }).encode('utf-8')))
            },
            {
                'body': MagicMock(read=MagicMock(return_value=json.dumps({
                    'content': [{'text': 'Support'}]
                }).encode('utf-8')))
            }
        ]

        row = {'comment': 'I support this'}
        analysis_columns = [{
            'name': 'support',
            'type': 'categorized',
            'options': [
                {'value': 'Support', 'description': 'In favor'},
                {'value': 'Oppose', 'description': 'Against'}
            ]
        }]

        _process_single_row(row, analysis_columns)

        # Verify both calls used temperature=0
        self.assertGreaterEqual(mock_bedrock.invoke_model.call_count, 2)
        for call in mock_bedrock.invoke_model.call_args_list:
            body = json.loads(call[1]['body'])
            self.assertEqual(body.get('temperature'), 0,
                             f"All categorized + retry calls should use temperature=0, got body={body}")

    @patch('handler._get_bedrock_runtime')
    def test_examples_are_rendered_into_prompt(self, mock_get_bedrock):
        """Few-shot examples on a categorized column appear in the prompt as an <examples> block."""
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=MagicMock(return_value=json.dumps({
                'content': [{'text': json.dumps({'support': 'Support'})}]
            }).encode('utf-8')))
        }

        row = {'comment': 'I support legalization'}
        analysis_columns = [{
            'name': 'support',
            'type': 'categorized',
            'options': [
                {'value': 'Support', 'description': 'In favor'},
                {'value': 'Oppose', 'description': 'Against'}
            ],
            'examples': [
                {'commentText': 'Legalize cannabis now!', 'label': 'Support'},
                {'commentText': 'Cannabis should remain illegal.', 'label': 'Oppose'}
            ]
        }]

        _process_single_row(row, analysis_columns)

        prompt = json.loads(mock_bedrock.invoke_model.call_args[1]['body'])['messages'][0]['content']
        self.assertIn('<examples>', prompt, f"Expected <examples> block in prompt:\n{prompt}")
        self.assertIn('</examples>', prompt)
        self.assertIn('Legalize cannabis now!', prompt)
        self.assertIn('Cannabis should remain illegal.', prompt)
        # Each example should pair the comment text with its expected label
        self.assertIn('Support', prompt)
        self.assertIn('Oppose', prompt)

    @patch('handler._get_bedrock_runtime')
    def test_no_examples_omits_examples_block(self, mock_get_bedrock):
        """When no examples are supplied, the prompt does not contain an <examples> block."""
        mock_bedrock = MagicMock()
        mock_get_bedrock.return_value = mock_bedrock
        mock_bedrock.invoke_model.return_value = {
            'body': MagicMock(read=MagicMock(return_value=json.dumps({
                'content': [{'text': json.dumps({'support': 'Support'})}]
            }).encode('utf-8')))
        }

        row = {'comment': 'Test'}
        analysis_columns = [{
            'name': 'support',
            'type': 'categorized',
            'options': [
                {'value': 'Support', 'description': 'In favor'},
                {'value': 'Oppose', 'description': 'Against'}
            ]
        }]

        _process_single_row(row, analysis_columns)

        prompt = json.loads(mock_bedrock.invoke_model.call_args[1]['body'])['messages'][0]['content']
        self.assertNotIn('<examples>', prompt)

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

    def test_prompt_includes_all_columns(self):
        """Test that prompt includes all analysis column instructions."""
        with patch('handler._get_bedrock_runtime') as mock_get_bedrock:
            mock_bedrock = MagicMock()
            mock_get_bedrock.return_value = mock_bedrock
            
            mock_response = {
                'body': MagicMock(
                    read=MagicMock(return_value=json.dumps({
                        'content': [{'text': json.dumps({'col1': 'val1', 'col2': 'val2', 'col3': 'val3'})}]
                    }).encode('utf-8'))
                )
            }
            mock_bedrock.invoke_model.return_value = mock_response
            
            row = {'comment': 'Test comment'}
            analysis_columns = [
                {'name': 'col1', 'instructions': 'Instruction 1'},
                {'name': 'col2', 'instructions': 'Instruction 2'},
                {'name': 'col3', 'instructions': 'Instruction 3'}
            ]
            
            _process_single_row(row, analysis_columns)
            
            # Get the prompt from the call
            call_args = mock_bedrock.invoke_model.call_args
            body = json.loads(call_args[1]['body'])
            prompt = body['messages'][0]['content']
            
            # Verify all instructions are in prompt
            self.assertIn('Instruction 1', prompt)
            self.assertIn('Instruction 2', prompt)
            self.assertIn('Instruction 3', prompt)


class TestInitialProcessRoutesToPreview(unittest.TestCase):
    """The initial POST /process call should kick off the preview phase when applicable."""

    def setUp(self):
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'

    @patch('boto3.client')
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

        invoke_payload = json.loads(mock_lambda.invoke.call_args[1]['Payload'])
        self.assertEqual(invoke_payload.get('phase'), 'preview')

    @patch('boto3.client')
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

        invoke_payload = json.loads(mock_lambda.invoke.call_args[1]['Payload'])
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

    @patch('handler._get_dynamodb')
    def test_returns_404_when_job_does_not_exist(self, mock_dynamo):
        # DynamoDB returns no Item
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        event = self._build_event(str(uuid.uuid4()))
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 404)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'JOB_NOT_FOUND')

    @patch('handler._get_dynamodb')
    def test_returns_409_when_job_is_not_in_preview_ready_state(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'jobId': 'abc', 'status': 'completed'}
        }
        mock_dynamo.return_value.Table.return_value = mock_table

        event = self._build_event(str(uuid.uuid4()))
        response = lambda_handler(event, None)
        self.assertEqual(response['statusCode'], 409)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'INVALID_JOB_STATE')

    @patch('boto3.client')
    @patch('handler._get_dynamodb')
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
        mock_dynamo.return_value.Table.return_value = mock_table
        mock_lambda = MagicMock()
        mock_boto_client.return_value = mock_lambda

        ctx = MagicMock()
        ctx.function_name = 'PublicCommentAnalyzer-RowProcessor-test'
        event = self._build_event(job_id)
        response = lambda_handler(event, ctx)

        self.assertEqual(response['statusCode'], 200)
        # Must have invoked self async with phase=confirm
        invoke_call = mock_lambda.invoke.call_args
        self.assertEqual(invoke_call[1]['InvocationType'], 'Event')
        payload = json.loads(invoke_call[1]['Payload'])
        self.assertTrue(payload.get('asyncProcessing'))
        self.assertEqual(payload.get('phase'), 'confirm')
        self.assertEqual(payload.get('jobId'), job_id)


if __name__ == '__main__':
    unittest.main()
