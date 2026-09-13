"""Provider-neutral regression tests for partial results and bounded retries."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'shared'))
sys.path.insert(0, str(Path(__file__).parent))
import handler
from inference import InferenceError, InferenceLimitError
from file_parser import ParsedFile


class TestErrorHandling(unittest.TestCase):
    @patch('handler._update_job_progress')
    @patch('handler.time.sleep')
    @patch('handler.invoke_text')
    def test_partial_results_with_error_annotations(self, invoke, sleep, update):
        source = ParsedFile(headers=['comment', 'author'], rows=[
            {'comment': 'Good proposal', 'author': 'John'},
            {'comment': 'Bad idea', 'author': 'Jane'},
            {'comment': 'Interesting', 'author': 'Bob'},
        ], row_count=3)
        def classify(prompt, **kwargs):
            if 'Bad idea' in prompt:
                raise InferenceError('Provider temporarily unavailable')
            return json.dumps({'sentiment': 'positive' if 'Good proposal' in prompt else 'neutral'})
        invoke.side_effect = classify
        rows = handler._process_rows('test-job', source, [{'name': 'sentiment', 'instructions': 'Analyze sentiment'}])
        self.assertEqual([row['author'] for row in rows], ['John', 'Jane', 'Bob'])
        self.assertEqual(rows[0]['sentiment'], 'positive')
        self.assertEqual(rows[1]['sentiment'], '')
        self.assertIn('Processing failed', rows[1]['_error'])
        self.assertEqual(rows[2]['sentiment'], 'neutral')
        self.assertEqual(rows[0]['_error'], '')
        self.assertEqual(invoke.call_count, 5)
        self.assertEqual(source.rows[1], {'comment': 'Bad idea', 'author': 'Jane'})

    @patch('handler.time.sleep')
    @patch('handler.invoke_text', side_effect=InferenceError('Test provider error'))
    def test_error_logging_structure(self, invoke, sleep):
        with self.assertLogs(handler.logger, level='WARNING') as logs:
            with self.assertRaises(InferenceError):
                handler._process_single_row({'comment': 'PRIVATE_COMMENT'}, [{'name': 'sentiment', 'instructions': 'Analyze'}])
        self.assertNotIn('PRIVATE_COMMENT', '\n'.join(logs.output))
        self.assertEqual(invoke.call_count, 3)

    @patch('handler.time.sleep')
    @patch('handler.invoke_text')
    def test_retry_with_exponential_backoff(self, invoke, sleep):
        invoke.side_effect = [InferenceError('temporary'), InferenceError('temporary'), '{"sentiment":"positive"}']
        result = handler._process_single_row({'comment': 'Test'}, [{'name': 'sentiment', 'instructions': 'Analyze'}])
        self.assertEqual(result['sentiment'], 'positive')
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertGreaterEqual(sleep.call_args_list[1].args[0], 2)

    @patch('handler.time.sleep')
    @patch('handler.invoke_text', return_value='This is not valid JSON')
    def test_invalid_json_response_handling(self, invoke, sleep):
        with self.assertRaisesRegex(InferenceError, 'three bounded attempts'):
            handler._process_single_row({'comment': 'Test'}, [{'name': 'sentiment', 'instructions': 'Analyze'}])
        self.assertEqual(invoke.call_count, 3)

    @patch('handler.time.sleep')
    @patch('handler.invoke_text', side_effect=InferenceLimitError('Inference budget reached'))
    def test_budget_exhaustion_is_not_retried(self, invoke, sleep):
        with self.assertRaises(InferenceLimitError):
            handler._process_single_row({'comment': 'Test'}, [{'name': 'sentiment', 'instructions': 'Analyze'}])
        self.assertEqual(invoke.call_count, 1)
        sleep.assert_not_called()
