"""Unit tests for DynamoDB client."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from dynamodb_client import DynamoDBClient, JobStatus


@pytest.fixture
def mock_table():
    """Create a mock DynamoDB table."""
    return MagicMock()


@pytest.fixture
def dynamodb_client(mock_table):
    """Create a DynamoDB client with mocked table."""
    with patch('dynamodb_client.boto3') as mock_boto3:
        mock_resource = MagicMock()
        mock_boto3.resource.return_value = mock_resource
        mock_resource.Table.return_value = mock_table
        
        client = DynamoDBClient(table_name='test-table')
        return client


def test_create_job(dynamodb_client, mock_table):
    """Test creating a new job record."""
    job_id = 'test-job-123'
    file_id = 'test-file-456'
    total_rows = 100
    analysis_columns = [
        {'name': 'sentiment', 'instructions': 'Analyze sentiment'},
        {'name': 'category', 'instructions': 'Categorize comment'}
    ]
    input_file_key = 'uploads/test-file-456/input.csv'
    file_type = 'csv'
    
    result = dynamodb_client.create_job(
        job_id=job_id,
        file_id=file_id,
        total_rows=total_rows,
        analysis_columns=analysis_columns,
        input_file_key=input_file_key,
        file_type=file_type
    )
    
    # Verify put_item was called
    mock_table.put_item.assert_called_once()
    
    # Verify the job record structure
    assert result['jobId'] == job_id
    assert result['fileId'] == file_id
    assert result['status'] == JobStatus.PENDING
    assert result['totalRows'] == total_rows
    assert result['completedRows'] == 0
    assert result['analysisColumns'] == analysis_columns
    assert result['inputFileKey'] == input_file_key
    assert result['fileType'] == file_type
    assert result['outputFileKey'] == ''
    assert result['aggregateAnalysis'] == ''
    assert 'createdAt' in result
    assert 'updatedAt' in result
    assert result['errors'] == []
    assert 'ttl' in result


def test_get_job(dynamodb_client, mock_table):
    """Test retrieving a job record."""
    job_id = 'test-job-123'
    expected_job = {
        'jobId': job_id,
        'status': JobStatus.PROCESSING,
        'totalRows': 100,
        'completedRows': 50
    }
    
    mock_table.get_item.return_value = {'Item': expected_job}
    
    result = dynamodb_client.get_job(job_id)
    
    mock_table.get_item.assert_called_once_with(Key={'jobId': job_id})
    assert result == expected_job


def test_get_job_not_found(dynamodb_client, mock_table):
    """Test retrieving a non-existent job."""
    job_id = 'non-existent-job'
    mock_table.get_item.return_value = {}
    
    result = dynamodb_client.get_job(job_id)
    
    assert result is None


def test_update_job_status(dynamodb_client, mock_table):
    """Test updating job status."""
    job_id = 'test-job-123'
    new_status = JobStatus.PROCESSING
    completed_rows = 50
    
    dynamodb_client.update_job_status(
        job_id=job_id,
        status=new_status,
        completed_rows=completed_rows
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['Key'] == {'jobId': job_id}
    assert ':status' in call_args[1]['ExpressionAttributeValues']
    assert call_args[1]['ExpressionAttributeValues'][':status'] == new_status
    assert call_args[1]['ExpressionAttributeValues'][':completed'] == completed_rows


def test_update_job_status_with_errors(dynamodb_client, mock_table):
    """Test updating job status with errors."""
    job_id = 'test-job-123'
    new_status = JobStatus.FAILED
    errors = [
        {'message': 'Row 5 failed', 'rowNumber': 5},
        {'message': 'Row 10 failed', 'rowNumber': 10}
    ]
    
    dynamodb_client.update_job_status(
        job_id=job_id,
        status=new_status,
        errors=errors
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['ExpressionAttributeValues'][':errors'] == errors


def test_update_job_progress(dynamodb_client, mock_table):
    """Test updating job progress."""
    job_id = 'test-job-123'
    completed_rows = 75
    
    dynamodb_client.update_job_progress(
        job_id=job_id,
        completed_rows=completed_rows
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['Key'] == {'jobId': job_id}
    assert call_args[1]['ExpressionAttributeValues'][':completed'] == completed_rows


def test_update_output_file(dynamodb_client, mock_table):
    """Test updating output file key."""
    job_id = 'test-job-123'
    output_file_key = 'results/test-job-123/output.csv'
    
    dynamodb_client.update_output_file(
        job_id=job_id,
        output_file_key=output_file_key
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['Key'] == {'jobId': job_id}
    assert call_args[1]['ExpressionAttributeValues'][':output'] == output_file_key


def test_update_aggregate_analysis(dynamodb_client, mock_table):
    """Test updating aggregate analysis."""
    job_id = 'test-job-123'
    analysis = 'Overall sentiment is positive with 65% favorable comments.'
    
    dynamodb_client.update_aggregate_analysis(
        job_id=job_id,
        aggregate_analysis=analysis
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['Key'] == {'jobId': job_id}
    assert call_args[1]['ExpressionAttributeValues'][':analysis'] == analysis


def test_add_job_error(dynamodb_client, mock_table):
    """Test adding an error to a job."""
    job_id = 'test-job-123'
    error_message = 'Bedrock API call failed'
    row_number = 42
    
    # Mock get_job to return existing job with errors
    existing_job = {
        'jobId': job_id,
        'errors': [{'message': 'Previous error', 'rowNumber': 10}]
    }
    mock_table.get_item.return_value = {'Item': existing_job}
    
    dynamodb_client.add_job_error(
        job_id=job_id,
        error_message=error_message,
        row_number=row_number
    )
    
    # Verify get_item was called
    mock_table.get_item.assert_called_once_with(Key={'jobId': job_id})
    
    # Verify update_item was called
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    errors = call_args[1]['ExpressionAttributeValues'][':errors']
    assert len(errors) == 2
    assert errors[1]['message'] == error_message
    assert errors[1]['rowNumber'] == row_number
    assert 'timestamp' in errors[1]


def test_add_job_error_without_row_number(dynamodb_client, mock_table):
    """Test adding an error without row number."""
    job_id = 'test-job-123'
    error_message = 'General processing error'
    
    existing_job = {'jobId': job_id, 'errors': []}
    mock_table.get_item.return_value = {'Item': existing_job}
    
    dynamodb_client.add_job_error(
        job_id=job_id,
        error_message=error_message
    )
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    errors = call_args[1]['ExpressionAttributeValues'][':errors']
    assert len(errors) == 1
    assert errors[0]['message'] == error_message
    assert 'rowNumber' not in errors[0]


def test_increment_completed_rows(dynamodb_client, mock_table):
    """Test atomically incrementing completed rows."""
    job_id = 'test-job-123'
    
    dynamodb_client.increment_completed_rows(job_id=job_id, increment=5)
    
    mock_table.update_item.assert_called_once()
    call_args = mock_table.update_item.call_args
    
    assert call_args[1]['Key'] == {'jobId': job_id}
    assert 'ADD completedRows :inc' in call_args[1]['UpdateExpression']
    assert call_args[1]['ExpressionAttributeValues'][':inc'] == 5


def test_get_job_progress(dynamodb_client, mock_table):
    """Test getting job progress information."""
    job_id = 'test-job-123'
    job_data = {
        'jobId': job_id,
        'status': JobStatus.PROCESSING,
        'totalRows': 100,
        'completedRows': 75,
        'errors': []
    }
    
    mock_table.get_item.return_value = {'Item': job_data}
    
    result = dynamodb_client.get_job_progress(job_id)
    
    assert result['jobId'] == job_id
    assert result['status'] == JobStatus.PROCESSING
    assert result['progress'] == 75.0
    assert result['completedRows'] == 75
    assert result['totalRows'] == 100
    assert result['errors'] == []


def test_get_job_progress_not_found(dynamodb_client, mock_table):
    """Test getting progress for non-existent job."""
    job_id = 'non-existent-job'
    mock_table.get_item.return_value = {}
    
    result = dynamodb_client.get_job_progress(job_id)
    
    assert result['status'] == 'not_found'
    assert result['progress'] == 0
    assert result['completedRows'] == 0
    assert result['totalRows'] == 0


def test_get_job_progress_zero_rows(dynamodb_client, mock_table):
    """Test progress calculation with zero total rows."""
    job_id = 'test-job-123'
    job_data = {
        'jobId': job_id,
        'status': JobStatus.PENDING,
        'totalRows': 0,
        'completedRows': 0,
        'errors': []
    }
    
    mock_table.get_item.return_value = {'Item': job_data}
    
    result = dynamodb_client.get_job_progress(job_id)
    
    assert result['progress'] == 0


def test_client_initialization_without_table_name():
    """Test that client raises error if table name not provided."""
    with patch('dynamodb_client.boto3'):
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="Table name must be provided"):
                DynamoDBClient()


def test_client_initialization_with_env_var():
    """Test client initialization with environment variable."""
    with patch('dynamodb_client.boto3') as mock_boto3:
        mock_resource = MagicMock()
        mock_boto3.resource.return_value = mock_resource
        
        with patch.dict('os.environ', {'JOBS_TABLE': 'env-table-name'}):
            client = DynamoDBClient()
            assert client.table_name == 'env-table-name'
