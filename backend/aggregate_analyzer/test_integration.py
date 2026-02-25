"""Integration test for aggregate analyzer with full workflow."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Import handler and shared modules
import handler
from file_parser import ParsedFile
from file_writer import FileWriter


class TestAggregateAnalyzerIntegration(unittest.TestCase):
    """Integration tests for aggregate analyzer full workflow."""
    
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
    def test_full_aggregate_analysis_workflow(self, mock_get_dynamodb, 
                                              mock_get_s3, mock_get_bedrock):
        """Test complete workflow from job retrieval to analysis generation."""
        # Create sample processed data
        sample_data = ParsedFile(
            headers=['comment', 'author', 'sentiment', 'category'],
            rows=[
                {'comment': 'I support this proposal', 'author': 'John', 
                 'sentiment': 'positive', 'category': 'support'},
                {'comment': 'This is concerning', 'author': 'Jane', 
                 'sentiment': 'negative', 'category': 'concern'},
                {'comment': 'I have mixed feelings', 'author': 'Bob', 
                 'sentiment': 'neutral', 'category': 'mixed'},
                {'comment': 'Strongly in favor', 'author': 'Alice', 
                 'sentiment': 'positive', 'category': 'support'},
                {'comment': 'Strongly opposed', 'author': 'Charlie', 
                 'sentiment': 'negative', 'category': 'oppose'},
            ],
            row_count=5
        )
        
        # Write sample data to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
            temp_file_path = tmp.name
            writer = FileWriter()
            writer.write(sample_data.headers, sample_data.rows, temp_file_path, 'csv')
        
        # Mock DynamoDB
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'jobId': 'test-job-123',
                'status': 'completed',
                'outputFileKey': 'results/test-job-123/output.csv',
                'analysisColumns': [
                    {'name': 'sentiment', 'instructions': 'Analyze sentiment as positive, negative, or neutral'},
                    {'name': 'category', 'instructions': 'Categorize as support, oppose, concern, or mixed'}
                ]
            }
        }
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        
        # Mock S3
        mock_s3_client = Mock()
        mock_s3_client.download_file.side_effect = lambda bucket, key, path: \
            os.system(f'cp {temp_file_path} {path}')
        mock_s3_client.generate_presigned_url.return_value = 'https://s3.amazonaws.com/presigned-url'
        mock_get_s3.return_value = mock_s3_client
        
        # Mock Bedrock
        aggregate_analysis_text = """
Overall Sentiment Distribution:
- Positive: 2 comments (40%)
- Negative: 2 comments (40%)
- Neutral: 1 comment (20%)

Key Themes and Patterns:
The comments show a polarized response with equal numbers of positive and negative sentiments.
The main categories are support (40%) and opposition (40%), with some concerns and mixed feelings.

Notable Trends:
Strong language is used on both sides ("Strongly in favor" vs "Strongly opposed"), 
indicating passionate opinions on this topic.

Quantitative Summary:
- Total comments: 5
- Support category: 40%
- Oppose category: 20%
- Concern category: 20%
- Mixed category: 20%
"""
        
        mock_response = {
            'body': MagicMock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': aggregate_analysis_text}]
        }).encode('utf-8')
        
        mock_bedrock_client = Mock()
        mock_bedrock_client.invoke_model.return_value = mock_response
        mock_get_bedrock.return_value = mock_bedrock_client
        
        # Execute handler
        event = {'pathParameters': {'jobId': 'test-job-123'}, 'asyncAnalysis': True}
        response = handler.lambda_handler(event, None)
        
        # Verify response
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        
        # Check that response contains expected fields
        self.assertIn('downloadUrl', body)
        self.assertIn('aggregateAnalysis', body)
        self.assertEqual(body['downloadUrl'], 'https://s3.amazonaws.com/presigned-url')
        self.assertIn('Overall Sentiment Distribution', body['aggregateAnalysis'])
        self.assertIn('40%', body['aggregateAnalysis'])
        
        # Verify Bedrock was called with Claude Opus model
        bedrock_call_args = mock_bedrock_client.invoke_model.call_args
        self.assertEqual(bedrock_call_args[1]['modelId'], handler.CLAUDE_OPUS_MODEL_ID)
        
        # Verify prompt contains data summary
        bedrock_body = json.loads(bedrock_call_args[1]['body'])
        prompt = bedrock_body['messages'][0]['content']
        self.assertIn('Total Comments: 5', prompt)
        self.assertIn('sentiment:', prompt)
        self.assertIn('category:', prompt)
        
        # Verify DynamoDB was updated with analysis
        update_call_args = mock_table.update_item.call_args
        self.assertEqual(update_call_args[1]['Key'], {'jobId': 'test-job-123'})
        self.assertIn('aggregateAnalysis', update_call_args[1]['UpdateExpression'])
        
        # Clean up
        os.unlink(temp_file_path)
    
    def test_data_formatting_with_large_dataset(self):
        """Test data formatting handles large datasets efficiently."""
        # Create large dataset
        rows = []
        for i in range(100):
            rows.append({
                'comment': f'Comment {i}',
                'sentiment': 'positive' if i % 3 == 0 else ('negative' if i % 3 == 1 else 'neutral'),
                'rating': str((i % 5) + 1)
            })
        
        parsed_file = ParsedFile(
            headers=['comment', 'sentiment', 'rating'],
            rows=rows,
            row_count=100
        )
        
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Analyze sentiment'},
            {'name': 'rating', 'instructions': 'Rate 1-5'}
        ]
        
        formatted_data = handler._format_data_for_analysis(parsed_file, analysis_columns)
        
        # Verify formatted data contains summary
        self.assertIn('Total Comments: 100', formatted_data)
        self.assertIn('sentiment:', formatted_data)
        self.assertIn('rating:', formatted_data)
        
        # Verify percentages are calculated
        self.assertIn('%', formatted_data)
        
        # Verify sample size is limited (not all 100 rows)
        sample_count = formatted_data.count('Sample')
        self.assertLessEqual(sample_count, 11)  # Max 10 samples, word appears once per sample
    
    def test_prompt_construction_requirements(self):
        """Test that prompt meets requirements 6.1, 6.2, 6.3."""
        formatted_data = """Total Comments: 50
sentiment: positive 60%, negative 30%, neutral 10%"""
        
        analysis_columns = [
            {'name': 'sentiment', 'instructions': 'Categorize sentiment'},
            {'name': 'theme', 'instructions': 'Identify main theme'}
        ]
        
        prompt = handler._construct_aggregate_prompt(formatted_data, analysis_columns)
        
        # Requirement 6.2: Request sentiment distribution and key themes
        self.assertIn('Overall Sentiment Distribution', prompt)
        self.assertIn('Key Themes and Patterns', prompt)
        
        # Requirement 6.4: Request quantitative summaries
        self.assertIn('Quantitative Summary Statistics', prompt)
        self.assertIn('percentages', prompt)
        
        # Verify analysis column instructions are included
        self.assertIn('Categorize sentiment', prompt)
        self.assertIn('Identify main theme', prompt)
        
        # Verify formatted data is included
        self.assertIn(formatted_data, prompt)


if __name__ == '__main__':
    unittest.main()
