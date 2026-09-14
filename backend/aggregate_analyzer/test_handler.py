"""Unit tests for aggregate analyzer handler."""

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
        os.environ['ALLOWED_ORIGIN'] = 'http://localhost:4200'
    
    def test_missing_job_id(self):
        """Test handler with missing jobId."""
        event = {'pathParameters': {}}
        
        response = handler.lambda_handler(event, None)
        
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertEqual(body['error']['code'], 'MISSING_JOB_ID')
    
    @patch('handler.get_job_store')
    def test_job_not_found(self, get_store):
        get_store.return_value.get.return_value = None
        response = handler.lambda_handler({'pathParameters': {'jobId': '123e4567-e89b-42d3-a456-426614174000'}}, None)
        self.assertEqual(response['statusCode'], 404)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'JOB_NOT_FOUND')
    
    @patch('handler.get_job_store')
    def test_job_not_completed(self, get_store):
        get_store.return_value.get.return_value = {'status': 'processing'}
        response = handler.lambda_handler({'pathParameters': {'jobId': '123e4567-e89b-42d3-a456-426614174000'}}, None)
        self.assertEqual(response['statusCode'], 400)
        self.assertEqual(json.loads(response['body'])['error']['code'], 'JOB_NOT_COMPLETED')
    
    @patch('handler.get_job_store')
    @patch('handler._generate_presigned_url', return_value='http://localhost/api/download/test')
    def test_cached_analysis(self, signed_url, get_store):
        get_store.return_value.get.return_value = {'status': 'completed', 'outputFileKey': 'results/test/output.csv',
                                                   'aggregateAnalysis': 'Cached analysis text'}
        response = handler.lambda_handler({'pathParameters': {'jobId': '123e4567-e89b-42d3-a456-426614174000'}}, None)
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(json.loads(response['body'])['aggregateAnalysis'], 'Cached analysis text')
        self.assertEqual(json.loads(response['body'])['downloadUrl'], signed_url.return_value)
    
    def test_get_file_type(self):
        """Test file type extraction from object key."""
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
        """Test prompt construction for the summary integration."""
        formatted_data = "Total Comments: 100\nsentiment: positive 60%, negative 40%"
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment as positive, negative, or neutral'}
        ]
        
        prompt = handler._construct_aggregate_prompt(formatted_data, analysis_columns)
        
        # Check that prompt contains expected elements
        self.assertIn('aggregate analysis', prompt)
        self.assertIn('sentiment', prompt)
        self.assertIn('Analyze sentiment as positive, negative, or neutral', prompt)
        self.assertIn(formatted_data, prompt)
        self.assertIn('Categorized Column Breakdown', prompt)
        self.assertIn('Open Text Themes and Patterns', prompt)
    
    @patch('handler.invoke_text_with_retries', return_value='Aggregate analysis result')
    def test_call_summary_model_success(self, invoke):
        result = handler._call_summary_model('Test prompt')
        self.assertIn('Aggregate analysis result', result)
        self.assertTrue(result.startswith('**AI-generated draft'))
        invoke.assert_called_once_with('Test prompt', role='summary', max_tokens=4096)
    
    @patch('time.sleep')
    @patch('inference.invoke_text')
    def test_call_summary_model_retry(self, invoke, sleep):
        from inference import InferenceError
        invoke.side_effect = [InferenceError('temporary'), InferenceError('temporary'), 'Success after retries']
        result = handler._call_summary_model('Test prompt')
        self.assertIn('Success after retries', result)
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
    
    @patch('handler.get_job_store')
    def test_update_job_with_analysis(self, get_store):
        handler._update_job_with_analysis('123e4567-e89b-42d3-a456-426614174000', 'Analysis text')
        call = get_store.return_value.update.call_args
        self.assertEqual(call.args[0], '123e4567-e89b-42d3-a456-426614174000')
        self.assertEqual(call.args[1]['aggregateAnalysis'], 'Analysis text')
        self.assertEqual(call.args[1]['analysisStatus'], 'completed')
    
    @patch('handler.get_object_store')
    def test_generate_presigned_url(self, get_store):
        get_store.return_value.signed_url.return_value = 'http://localhost/api/download/test'
        self.assertEqual(handler._generate_presigned_url('results/job/output.csv'), 'http://localhost/api/download/test')
        get_store.return_value.signed_url.assert_called_once_with('results/job/output.csv', expires=3600)


if __name__ == '__main__':
    unittest.main()
