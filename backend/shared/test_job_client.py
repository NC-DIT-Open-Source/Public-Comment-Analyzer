"""Regression tests for the stable job API against real portable persistence.

The historical filename stays to preserve test-suite discovery during migration.
"""

from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
from adapters.local import LocalRuntime
from job_client import JobClient, JobStatus


@pytest.fixture
def client(tmp_path):
    return JobClient(LocalRuntime(tmp_path).jobs)


@pytest.fixture
def job(client):
    return client.create_job(str(uuid.uuid4()), str(uuid.uuid4()), 100,
        [{'name': 'sentiment', 'instructions': 'Analyze sentiment'}], 'uploads/input.csv', 'csv')


def test_create_job(client, job):
    assert client.get_job(job['jobId']) == job
    assert job['status'] == JobStatus.PENDING
    assert job['totalRows'] == 100 and job['completedRows'] == 0
    assert job['analysisColumns'][0]['name'] == 'sentiment'
    assert job['outputFileKey'] == job['aggregateAnalysis'] == ''
    assert job['errors'] == []
    assert all(name in job for name in ('createdAt', 'updatedAt', 'ttl', 'fileId', 'fileType'))


def test_get_job(client, job):
    assert client.get_job(job['jobId']) == job


def test_get_job_not_found(client):
    assert client.get_job(str(uuid.uuid4())) is None


def test_update_job_status(client, job):
    client.update_job_status(job['jobId'], JobStatus.PROCESSING, completed_rows=50)
    updated = client.get_job(job['jobId'])
    assert updated['status'] == JobStatus.PROCESSING and updated['completedRows'] == 50
    assert updated['analysisColumns'] == job['analysisColumns']


def test_update_job_status_with_errors(client, job):
    errors = [{'message': 'Row failed', 'rowNumber': 5}]
    client.update_job_status(job['jobId'], JobStatus.FAILED, errors=errors)
    assert client.get_job(job['jobId'])['errors'] == errors


def test_update_job_progress(client, job):
    client.update_job_progress(job['jobId'], 25)
    assert client.get_job(job['jobId'])['completedRows'] == 25


def test_update_output_file(client, job):
    client.update_output_file(job['jobId'], 'results/output.csv')
    assert client.get_job(job['jobId'])['outputFileKey'] == 'results/output.csv'


def test_update_aggregate_analysis(client, job):
    client.update_aggregate_analysis(job['jobId'], 'A draft analysis')
    assert client.get_job(job['jobId'])['aggregateAnalysis'] == 'A draft analysis'


def test_add_job_error(client, job):
    client.add_job_error(job['jobId'], 'Processing failed', row_number=5)
    error = client.get_job(job['jobId'])['errors'][0]
    assert error['rowNumber'] == 5 and error['message'] == 'Processing failed' and error['timestamp']


def test_add_job_error_without_row_number(client, job):
    client.add_job_error(job['jobId'], 'Processing failed')
    assert 'rowNumber' not in client.get_job(job['jobId'])['errors'][0]


def test_increment_completed_rows(client, job):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: client.increment_completed_rows(job['jobId']), range(20)))
    assert client.get_job(job['jobId'])['completedRows'] == 20


def test_get_job_progress(client, job):
    client.update_job_progress(job['jobId'], 50)
    status = client.get_job_progress(job['jobId'])
    assert status['totalRows'] == 100 and status['completedRows'] == 50 and status['progress'] == 50


def test_get_job_progress_not_found(client):
    assert client.get_job_progress(str(uuid.uuid4())) == {'status': 'not_found', 'progress': 0, 'completedRows': 0, 'totalRows': 0}


def test_get_job_progress_zero_rows(client, job):
    client.store.update(job['jobId'], {'totalRows': 0})
    assert client.get_job_progress(job['jobId'])['progress'] == 0


def test_client_initialization_without_table_name(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_RUNTIME', 'local')
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path))
    assert JobClient().store.database.parent == tmp_path


def test_client_initialization_with_explicit_store(client):
    assert JobClient(store=client.store).store is client.store
