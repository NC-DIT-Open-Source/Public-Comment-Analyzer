"""Integration test for aggregate analyzer with full workflow."""

import json
import os
import shutil
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
        os.environ['ALLOWED_ORIGIN'] = 'http://localhost:4200'
    
    @patch('handler.invoke_text_with_retries', return_value='Overall Sentiment Distribution: positive 40%, negative 40%, neutral 20%.')
    @patch('handler.get_object_store')
    @patch('handler.get_job_store')
    def test_full_aggregate_analysis_workflow(self, get_jobs, get_objects, invoke):
        job_id = '123e4567-e89b-42d3-a456-426614174000'
        get_jobs.return_value.get.return_value = {
            'jobId': job_id, 'status': 'completed', 'outputFileKey': f'results/{job_id}/output.csv',
            'analysisColumns': [{'name': 'sentiment', 'instructions': 'Analyze sentiment'}],
        }
        data = 'comment,sentiment\nComment 1,positive\nComment 2,negative\nComment 3,neutral\nComment 4,positive\nComment 5,negative\n'
        def download(key, destination):
            with open(destination, 'w') as output:
                output.write(data)
        get_objects.return_value.download.side_effect = download
        get_objects.return_value.signed_url.return_value = 'http://localhost/api/download/test'
        response = handler.lambda_handler({'pathParameters': {'jobId': job_id}, 'asyncAnalysis': True}, None)
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['downloadUrl'], 'http://localhost/api/download/test')
        self.assertIn('Overall Sentiment Distribution', body['aggregateAnalysis'])
        self.assertTrue(body['aggregateAnalysis'].startswith('**AI-generated draft'))
        prompt = invoke.call_args.args[0]
        self.assertIn('Total Comments: 5', prompt)
        self.assertIn('sentiment', prompt)
        self.assertEqual(invoke.call_args.kwargs['role'], 'summary')
        saved = get_jobs.return_value.update.call_args
        self.assertEqual(saved.args[0], job_id)
        self.assertEqual(saved.args[1]['aggregateAnalysis'], body['aggregateAnalysis'])
    
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
            {
                'name': 'sentiment',
                'type': 'categorized',
                'instructions': 'Analyze sentiment',
                'options': [
                    {'value': 'positive', 'description': 'Positive'},
                    {'value': 'negative', 'description': 'Negative'},
                    {'value': 'neutral', 'description': 'Neutral'}
                ]
            },
            {'name': 'rating', 'type': 'open_text', 'instructions': 'Rate 1-5'}
        ]
        
        formatted_data = handler._format_data_for_analysis(parsed_file, analysis_columns)
        
        # Verify formatted data contains summary
        self.assertIn('Total Comments: 100', formatted_data)
        self.assertIn('sentiment', formatted_data)
        self.assertIn('rating', formatted_data)
        
        # Verify categorized column has percentages
        self.assertIn('%', formatted_data)
        
        # Verify open text column uses map-reduce format (all values listed for <=150 rows)
        self.assertIn('rating — All 100 responses:', formatted_data)
        
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
        
        # Requirement 6.2: Request categorized breakdown and open text themes
        self.assertIn('Categorized Column Breakdown', prompt)
        self.assertIn('Open Text Themes and Patterns', prompt)
        
        # Requirement 6.4: Request quantitative summaries
        self.assertIn('Quantitative Summary', prompt)
        self.assertIn('percentages', prompt)
        
        # Verify analysis column instructions are included
        self.assertIn('Categorize sentiment', prompt)
        self.assertIn('Identify main theme', prompt)
        
        # Verify formatted data is included
        self.assertIn(formatted_data, prompt)


if __name__ == '__main__':
    unittest.main()
