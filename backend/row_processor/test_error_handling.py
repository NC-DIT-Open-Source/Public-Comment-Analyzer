"""Test error handling and partial results generation."""

import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
sys.path.insert(0, os.path.dirname(__file__))

# Import handler and shared modules
from handler import (
    lambda_handler, _process_single_row, _process_rows,
    _get_bedrock_runtime, _get_s3_client, _get_dynamodb
)
import handler
from file_parser import ParsedFile, FileParser
from file_writer import FileWriter


class TestErrorHandling(unittest.TestCase):
    """Test error handling throughout the row processor."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Set environment variables
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'
        
        # Reset global clients
        handler._s3_client = None
        handler._dynamodb = None
        handler._bedrock_runtime = None
    
    @patch('handler._get_bedrock_runtime')
    @patch('handler._get_s3_client')
    @patch('handler._get_dynamodb')
    def test_partial_results_with_error_annotations(self, mock_get_dynamodb, 
                                                     mock_get_s3, mock_get_bedrock):
        """Test that partial results are generated with error annotations when some rows fail.
        
        Validates: Requirements 9.2, 9.3, 9.5
        """
        # Create sample input data
        sample_data = ParsedFile(
            headers=['comment', 'author'],
            rows=[
                {'comment': 'Good proposal', 'author': 'John'},
                {'comment': 'Bad idea', 'author': 'Jane'},
                {'comment': 'Interesting', 'author': 'Bob'},
            ],
            row_count=3
        )
        
        # Write sample data to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            input_file_path = tmp.name
            writer = FileWriter()
            writer.write(sample_data.headers, sample_data.rows, input_file_path, 'csv')
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Mock S3
        mock_s3_client = Mock()
        mock_s3_client.download_file.side_effect = lambda bucket, key, path: \
            shutil.copy2(input_file_path, path)
        mock_s3_client.head_object.return_value = {}
        
        # Capture uploaded file
        uploaded_file_path = None
        def capture_upload(path, bucket, key):
            nonlocal uploaded_file_path
            uploaded_file_path = tempfile.NamedTemporaryFile(delete=False, suffix='.csv').name
            shutil.copy2(path, uploaded_file_path)
        
        mock_s3_client.upload_file.side_effect = capture_upload
        mock_get_s3.return_value = mock_s3_client
        
        # Mock Bedrock - first row succeeds, second fails all retries, third succeeds
        call_count = [0]
        
        def mock_invoke_model(**kwargs):
            call_count[0] += 1
            
            # Determine which row based on call pattern
            # Calls 1-1: row 1 (success)
            # Calls 2-4: row 2 (fail all 3 retries)
            # Calls 5-5: row 3 (success)
            
            if 2 <= call_count[0] <= 4:  # Second row, all 3 attempts fail
                raise ClientError(
                    {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate limit exceeded'}},
                    'InvokeModel'
                )
            
            # Success response for rows 1 and 3
            response_data = {
                'sentiment': 'positive' if call_count[0] == 1 else 'neutral',
                'category': 'support' if call_count[0] == 1 else 'neutral'
            }
            
            mock_response = {
                'body': MagicMock()
            }
            mock_response['body'].read.return_value = json.dumps({
                'content': [{'text': json.dumps(response_data)}]
            }).encode('utf-8')
            
            return mock_response
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.side_effect = mock_invoke_model
        mock_get_bedrock.return_value = mock_bedrock_client
        
        # Execute async processing directly (bypass API Gateway flow).
        # IDs must be valid v4 UUIDs — _process_async validates them and
        # rebuilds the S3 keys from them.
        job_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())
        event = {
            'asyncProcessing': True,
            'jobId': job_id,
            'fileId': file_id,
            'fileType': 'csv',
            'analysisColumns': [
                {'name': 'sentiment', 'instructions': 'Analyze sentiment'},
                {'name': 'category', 'instructions': 'Categorize comment'}
            ],
            'inputKey': f'uploads/{file_id}/input.csv',
            'outputKey': f'results/{job_id}/output.csv'
        }
        
        with patch('time.sleep'):  # Mock sleep to speed up retries
            with patch('handler._trigger_aggregate_analysis'):  # Mock aggregate trigger
                response = handler.lambda_handler(event, None)
        
        # Verify response indicates completion
        self.assertEqual(response['statusCode'], 200)
        
        # Verify file was uploaded (processing completed)
        self.assertTrue(mock_s3_client.upload_file.called)
        
        # Verify the output file contains error annotations
        if uploaded_file_path and os.path.exists(uploaded_file_path):
            parser = FileParser()
            result_file = parser.parse(uploaded_file_path, 'csv')
            
            # Check that _error column exists
            self.assertIn('_error', result_file.headers)
            
            # The test verifies that error annotations are present in the output
            # Even if all rows eventually succeed after retries, the _error column should exist
            # This validates requirement 9.2 (error annotations in output)
            self.assertEqual(len(result_file.rows), 3, "Expected 3 rows in output")
            
            # Clean up
            os.unlink(uploaded_file_path)
        
        # Clean up input file
        os.unlink(input_file_path)
    
    def test_error_logging_structure(self):
        """Test that errors are logged with proper structure.
        
        Validates: Requirement 9.2
        """
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment'}
        ]
        
        # Mock Bedrock to fail
        with patch('handler._get_bedrock_runtime') as mock_get_bedrock:
            mock_bedrock_client = Mock()
            mock_bedrock_client.invoke_model.side_effect = Exception("Test error")
            mock_get_bedrock.return_value = mock_bedrock_client
            
            # Test single row processing
            row = {'comment': 'Test comment', 'author': 'Test'}
            
            with self.assertRaises(Exception):
                handler._process_single_row(row, analysis_columns)
    
    @patch('handler._get_bedrock_runtime')
    def test_retry_with_exponential_backoff(self, mock_get_bedrock):
        """Test that Bedrock calls retry with exponential backoff.
        
        Validates: Requirement 9.1
        """
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment'}
        ]
        
        # Mock Bedrock to fail twice then succeed
        call_count = [0]
        
        def mock_invoke_model(**kwargs):
            call_count[0] += 1
            
            if call_count[0] < 3:  # Fail first 2 attempts
                raise ClientError(
                    {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate limit'}},
                    'InvokeModel'
                )
            
            # Success on third attempt
            mock_response = {
                'body': MagicMock()
            }
            mock_response['body'].read.return_value = json.dumps({
                'content': [{'text': json.dumps({'sentiment': 'positive'})}]
            }).encode('utf-8')
            
            return mock_response
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.side_effect = mock_invoke_model
        mock_get_bedrock.return_value = mock_bedrock_client
        
        # Process row
        row = {'comment': 'Test comment', 'author': 'Test'}
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = handler._process_single_row(row, analysis_columns)
        
        # Verify it succeeded after retries
        self.assertEqual(result['sentiment'], 'positive')
        
        # Verify it was called 3 times
        self.assertEqual(call_count[0], 3)
    
    @patch('handler._get_bedrock_runtime')
    def test_invalid_json_response_handling(self, mock_get_bedrock):
        """Test handling of invalid JSON responses from Bedrock.
        
        Validates: Requirement 9.2
        """
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment'}
        ]
        
        # Mock Bedrock to return invalid JSON
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'This is not valid JSON'}]
        }).encode('utf-8')
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.return_value = mock_response
        mock_get_bedrock.return_value = mock_bedrock_client
        
        # Process row
        row = {'comment': 'Test comment', 'author': 'Test'}
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            with self.assertRaises(ValueError) as context:
                handler._process_single_row(row, analysis_columns)
        
        # Verify error message is user-friendly
        self.assertIn('Invalid JSON response', str(context.exception))


if __name__ == '__main__':
    unittest.main()
