"""Real file parsing and budget preflight must happen before jobs are queued."""
import json
import os
from pathlib import Path
import shutil
from unittest.mock import Mock
import uuid

import pytest
import handler
import inference


@pytest.fixture
def process_context(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('LLM_'):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'budget'))
    monkeypatch.setenv('LLM_PROVIDER', 'openai')
    monkeypatch.setenv('LLM_MODEL', 'operator-model')
    monkeypatch.setenv('LLM_API_KEY', 'PRIVATE_TEST_SECRET')
    monkeypatch.setenv('LLM_BUDGET_USD', '1')
    monkeypatch.setenv('LLM_INPUT_COST_PER_MILLION', '1')
    monkeypatch.setenv('LLM_OUTPUT_COST_PER_MILLION', '2')
    monkeypatch.setenv('LLM_MAX_CALLS', '100')
    monkeypatch.setenv('ALLOWED_ORIGIN', 'http://localhost:4200')
    source = tmp_path / 'input.csv'
    source.write_text('comment\nPRIVATE_COMMENT one\nPRIVATE_COMMENT two\n')
    objects = Mock()
    objects.download.side_effect = lambda key, destination: shutil.copyfile(source, destination)
    monkeypatch.setattr(handler, 'get_object_store', lambda: objects)
    monkeypatch.setattr(handler, '_determine_file_type', lambda _: 'csv')
    create_job, enqueue = Mock(), Mock()
    monkeypatch.setattr(handler, '_create_job_record_quick', create_job)
    monkeypatch.setattr(handler, 'enqueue_task', enqueue)
    monkeypatch.setattr(inference, '_request', lambda *args: pytest.fail('Preflight must not call an AI provider'))
    event = {'body': json.dumps({'fileId': str(uuid.uuid4()), 'selectedCommentColumn': 'comment',
        'contextDescription': 'Synthetic test', 'analysisColumns': [
            {'name': 'Summary', 'type': 'open_text', 'instructions': 'Summarize the comment.'}]})}
    return event, create_job, enqueue, source


def test_insufficient_money_rejected_before_job_or_provider(process_context, monkeypatch):
    event, create_job, enqueue, _ = process_context
    monkeypatch.setenv('LLM_BUDGET_USD', '0.000001')
    response = handler.lambda_handler(event, None)
    assert response['statusCode'] == 409
    body = json.loads(response['body'])
    assert body['error']['code'] == 'INFERENCE_LIMIT'
    estimate = body['inferenceEstimate']
    assert estimate['minimumRequiredReservationUsd'] > estimate['remainingBudgetUsd']
    assert estimate['minimumCalls'] == 3
    assert 'PRIVATE_COMMENT' not in response['body'] and 'PRIVATE_TEST_SECRET' not in response['body']
    create_job.assert_not_called()
    enqueue.assert_not_called()
    assert inference.budget_status()['calls'] == 0


def test_insufficient_remaining_call_capacity_rejected(process_context, monkeypatch):
    event, create_job, enqueue, _ = process_context
    monkeypatch.setenv('LLM_MAX_CALLS', '3')
    inference._reserve('An earlier synthetic request', 50)
    response = handler.lambda_handler(event, None)
    assert response['statusCode'] == 409
    assert json.loads(response['body'])['inferenceEstimate']['remainingDeploymentCalls'] == 2
    create_job.assert_not_called()
    enqueue.assert_not_called()
    assert inference.budget_status()['calls'] == 1


def test_preflight_uses_production_prompts_and_is_additive(process_context):
    event, create_job, enqueue, _ = process_context
    response = handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['jobId'] and body['status'] == 'pending'
    estimate = body['inferenceEstimate']
    assert estimate['rows'] == 2 and estimate['minimumCalls'] == 3
    assert estimate['estimatedCallsIncludingRetries'] == 9
    columns = [{'name': 'Summary', 'type': 'open_text', 'instructions': 'Summarize the comment.'}]
    expected = sum(inference.estimate_call_cost(handler._prepare_row_request(
        {'comment': f'PRIVATE_COMMENT {label}'}, columns, 'comment', 'Synthetic test')[0], 500)
        for label in ('one', 'two'))
    assert estimate['rowFirstPassReservationUsd'] == float(expected)
    assert estimate['includesFullSummaryInput'] is False
    assert estimate['includesRetries'] is False
    assert 'PRIVATE_COMMENT' not in response['body'] and 'PRIVATE_TEST_SECRET' not in response['body']
    create_job.assert_called_once()
    enqueue.assert_called_once()
    assert inference.budget_status()['calls'] == 0


def test_preflight_does_not_require_maximum_retry_budget(process_context, monkeypatch):
    event, create_job, enqueue, _ = process_context
    monkeypatch.setenv('LLM_MAX_CALLS', '3')
    response = handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    estimate = json.loads(response['body'])['inferenceEstimate']
    assert estimate['estimatedCallsIncludingRetries'] > estimate['remainingDeploymentCalls']
    enqueue.assert_called_once()


def test_preflight_rejects_oversized_prompt_without_spending(process_context, monkeypatch):
    event, create_job, enqueue, _ = process_context
    monkeypatch.setenv('LLM_MAX_PROMPT_CHARS', '1000')
    body = json.loads(event['body'])
    body['analysisColumns'][0]['instructions'] = 'x' * 1200
    event['body'] = json.dumps(body)
    response = handler.lambda_handler(event, None)
    assert response['statusCode'] == 409
    create_job.assert_not_called()
    enqueue.assert_not_called()
    assert inference.budget_status()['calls'] == 0
