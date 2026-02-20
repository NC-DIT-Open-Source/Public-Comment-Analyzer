"""Unit tests for aggregate analyzer Lambda handler."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
sys.path.insert(0, os.path.dirname(__file__))

# Import handler
import handler


class TestAggregateAnalyzer(unittest.TestCase):
    """Test cases for aggregate analyzer handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Set environment variables
        os.environ['DATA_BUCKET'] = 'test-bucket'
        os.environ['JOBS_TABLE'] = 'test-table'
        
        # Reset global clients
        handler._s3_client = None
        handler._dynamodb = None
        handler._bedrock_runtime = None
    
    def test_missing_job_id(self):
        """Test handler with missing jobId."""
        event = {'pathParameters': {}}
        
        response = handler.lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'MISSING_JOB_ID')
    
    @patch('handler._get_dynamodb')
    def test_job_not_found(self, mock_get_dynamodb):
        """Test handler with non-existent job."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {}
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        event = {'pathParameters': {'jobId': 'test-job-123'}}
        
        response = handler.lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 404)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'JOB_NOT_FOUND')
    
    @patch('handler._get_dynamodb')
    def test_job_not_completed(self, mock_get_dynamodb):
        """Test handler with job that is still processing."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': 'test-job-123',
                'status': 'processing',
                'outputFileKey': 'results/test-job-123/output.csv'
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        event = {'pathParameters': {'jobId': 'test-job-123'}}
        
        response = handler.lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'JOB_NOT_COMPLETED')
    
    @patch('handler._get_dynamodb')
    @patch('handler._generate_presigned_url')
    def test_cached_analysis(self, mock_presigned_url, mock_get_dynamodb):
        """Test handler returns cached analysis if it exists."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': 'test-job-123',
                'status': 'completed',
                'outputFileKey': 'results/test-job-123/output.csv',
                'aggregateAnalysis': 'Cached analysis text',
                'analysisColumns': [{'name': 'sentiment', 'instructions': 'Analyze sentiment'}]
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Mock presigned URL
        mock_presigned_url.return_value = 'https://s3.amazonaws.com/presigned-url'
        
        event = {'pathParameters': {'jobId': 'test-job-123'}}
        
        response = handler.lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['aggregateAnalysis'], 'Cached analysis text')
        self.assertEqual(body['downloadUrl'], 'https://s3.amazonaws.com/presigned-url')
    
    def test_get_file_type(self):
        """Test file type extraction from S3 key."""
        self.assertEqual(handler._get_file_type('results/job-123/output.csv'), 'csv')
        self.assertEqual(handler._get_file_type('results/job-123/output.xlsx'), 'xlsx')
        
        with self.assertRaises(ValueError):
            handler._get_file_type('results/job-123/output.txt')
    
    def test_format_data_for_analysis(self):
        """Test data formatting for aggregate analysis."""
        from file_parser import ParsedFile
        
        # Create sample parsed file
        parsed_file = ParsedFile(
            headers=['comment', 'sentiment', 'rating'],
            rows=[
                {'comment': 'Great product', 'sentiment': 'positive', 'rating': '5'},
                {'comment': 'Not bad', 'sentiment': 'neutral', 'rating': '3'},
                {'comment': 'Terrible', 'sentiment': 'negative', 'rating': '1'},
                {'comment': 'Love it', 'sentiment': 'positive', 'rating': '5'},
            ],
            row_count=4
        )
        
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment'},
            {'name': 'rating', 'instructions': 'Rate 1-5'}
        ]
        
        formatted_data = handler._format_data_for_analysis(parsed_file, analysis_columns)
        
        # Check that formatted data contains expected elements
        self.assertIn('Total Comments: 4', formatted_data)
        self.assertIn('sentiment:', formatted_data)
        self.assertIn('rating:', formatted_data)
        self.assertIn('positive', formatted_data)
        self.assertIn('Sample', formatted_data)
    
    def test_construct_aggregate_prompt(self):
        """Test prompt construction for Claude Opus."""
        formatted_data = "Total Comments: 100\nsentiment: positive 60%, negative 40%"
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment as positive, negative, or neutral'}
        ]
        
        prompt = handler._construct_aggregate_prompt(formatted_data, analysis_columns)
        
        # Check that prompt contains expected elements
        self.assertIn('aggregate sentiment analysis', prompt)
        self.assertIn('sentiment', prompt)
        self.assertIn('Analyze sentiment as positive, negative, or neutral', prompt)
        self.assertIn(formatted_data, prompt)
        self.assertIn('Overall Sentiment Distribution', prompt)
        self.assertIn('Key Themes and Patterns', prompt)
    
    @patch('handler._get_bedrock_runtime')
    def test_call_bedrock_opus_success(self, mock_get_bedrock):
        """Test successful Bedrock call."""
        # Mock Bedrock response
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Aggregate analysis result'}]
        }).encode('utf-8')
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.return_value = mock_response
        mock_get_bedrock.return_value = mock_bedrock_client
        
        result = handler._call_bedrock_opus('Test prompt')
        
        self.assertEqual(result, 'Aggregate analysis result')
        
        # Verify Bedrock was called with correct model ID
        call_args = mock_bedrock_client.invoke_model.call_args
        self.assertEqual(call_args[1]['modelId'], handler.CLAUDE_OPUS_MODEL_ID)
    
    @patch('handler._get_bedrock_runtime')
    @patch('time.sleep')
    def test_call_bedrock_opus_retry(self, mock_sleep, mock_get_bedrock):
        """Test Bedrock call with retry logic."""
        # Mock Bedrock to fail twice then succeed
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Success after retries'}]
        }).encode('utf-8')
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.side_effect = [
            Exception('First failure'),
            Exception('Second failure'),
            mock_response
        ]
        mock_get_bedrock.return_value = mock_bedrock_client
        
        result = handler._call_bedrock_opus('Test prompt')
        
        self.assertEqual(result, 'Success after retries')
        self.assertEqual(mock_bedrock_client.invoke_model.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Two retries
    
    @patch('handler._get_dynamodb')
    def test_update_job_with_analysis(self, mock_get_dynamodb):
        """Test updating job record with aggregate analysis."""
        # Mock DynamoDB
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        handler._update_job_with_analysis('test-job-123', 'Analysis text')
        
        # Verify update_item was called
        mock_table.update_item.assert_called_once()
        call_args = mock_table.update_item.call_args
        self.assertEqual(call_args[1]['Key'], {'jobId': 'test-job-123'})
        self.assertIn('aggregateAnalysis', call_args[1]['UpdateExpression'])
    
    @patch('handler._get_s3_client')
    def test_generate_presigned_url(self, mock_get_s3):
        """Test presigned URL generation."""
        # Mock S3 client
        mock_s3_client = Mock()
        mock_s3_client.generate_presigned_url.return_value = 'https://presigned-url'
        mock_get_s3.return_value = mock_s3_client
        
        url = handler._generate_presigned_url('results/job-123/output.csv')
        
        self.assertEqual(url, 'https://presigned-url')
        
        # Verify S3 was called correctly
        call_args = mock_s3_client.generate_presigned_url.call_args
        self.assertEqual(call_args[0][0], 'get_object')
        self.assertEqual(call_args[1]['Params']['Key'], 'results/job-123/output.csv')


if __name__ == '__main__':
    unittest.main()
