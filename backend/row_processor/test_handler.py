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
    _process_single_row
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
        """More than 5 examples per column is rejected."""
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
                        {'commentText': f'Example {i}', 'label': 'Support'} for i in range(6)
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


if __name__ == '__main__':
    unittest.main()
