"""Unit tests for upload handler."""

import json
import base64
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Add the handler directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from handler import (
    lambda_handler,
    parse_multipart_form_data,
    get_file_extension,
    validate_file_format
)


class TestFileExtraction:
    """Test file extension and validation functions."""
    
    def test_get_file_extension_csv(self):
        """Test extracting CSV extension."""
        assert get_file_extension('test.csv') == 'csv'
        assert get_file_extension('data.CSV') == 'csv'
    
    def test_get_file_extension_xlsx(self):
        """Test extracting XLSX extension."""
        assert get_file_extension('test.xlsx') == 'xlsx'
        assert get_file_extension('data.XLSX') == 'xlsx'
    
    def test_get_file_extension_no_extension(self):
        """Test file without extension."""
        assert get_file_extension('testfile') == ''
    
    def test_validate_file_format_valid(self):
        """Test validation of valid formats."""
        assert validate_file_format('csv') is True
        assert validate_file_format('xlsx') is True
        assert validate_file_format('xls') is True
    
    def test_validate_file_format_invalid(self):
        """Test validation of invalid formats."""
        assert validate_file_format('txt') is False
        assert validate_file_format('pdf') is False
        assert validate_file_format('') is False


class TestMultipartParsing:
    """Test multipart form data parsing."""
    
    def test_parse_simple_csv(self):
        """Test parsing a simple CSV file upload."""
        # Create a simple multipart body
        boundary = 'boundary123'
        filename = 'test.csv'
        content = b'name,age\nJohn,30\nJane,25'
        
        body_parts = [
            f'--{boundary}',
            'Content-Disposition: form-data; name="file"; filename="test.csv"',
            'Content-Type: text/csv',
            '',
            content.decode('utf-8'),
            f'--{boundary}--'
        ]
        body = '\r\n'.join(body_parts)
        body_base64 = base64.b64encode(body.encode()).decode()
        
        content_type = f'multipart/form-data; boundary={boundary}'
        
        result = parse_multipart_form_data(body_base64, content_type)
        
        assert result['filename'] == filename
        assert b'name,age' in result['file']


class TestLambdaHandler:
    """Test Lambda handler function."""
    
    @patch('handler.s3_client')
    @patch('handler.FileParser')
    def test_upload_valid_csv(self, mock_parser_class, mock_s3):
        """Test uploading a valid CSV file."""
        # Setup mock parser
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parsed_file = MagicMock()
        mock_parsed_file.headers = ['name', 'age']
        mock_parsed_file.row_count = 2
        mock_parser.parse.return_value = mock_parsed_file
        
        # Create multipart request
        boundary = 'boundary123'
        content = b'name,age\nJohn,30\nJane,25'
        
        body_parts = [
            f'--{boundary}',
            'Content-Disposition: form-data; name="file"; filename="test.csv"',
            'Content-Type: text/csv',
            '',
            content.decode('utf-8'),
            f'--{boundary}--'
        ]
        body = '\r\n'.join(body_parts)
        body_base64 = base64.b64encode(body.encode()).decode()
        
        event = {
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            },
            'body': body_base64,
            'isBase64Encoded': True
        }
        
        # Set environment variable
        with patch.dict(os.environ, {'DATA_BUCKET': 'test-bucket'}):
            response = lambda_handler(event, None)
        
        # Verify response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'fileId' in body
        assert body['columns'] == ['name', 'age']
        assert body['rowCount'] == 2
        assert body['filename'] == 'test.csv'
        assert body['fileType'] == 'csv'
        
        # Verify S3 upload was called
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args[1]['Bucket'] == 'test-bucket'
        assert 'uploads/' in call_args[1]['Key']
        assert call_args[1]['Key'].endswith('/input.csv')
    
    def test_upload_invalid_content_type(self):
        """Test upload with invalid content type."""
        event = {
            'headers': {
                'content-type': 'application/json'
            },
            'body': '{}',
            'isBase64Encoded': False
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_CONTENT_TYPE'
    
    @patch('handler.s3_client')
    @patch('handler.FileParser')
    def test_upload_invalid_file_format(self, mock_parser_class, mock_s3):
        """Test uploading a file with invalid format."""
        boundary = 'boundary123'
        content = b'This is a text file'
        
        body_parts = [
            f'--{boundary}',
            'Content-Disposition: form-data; name="file"; filename="test.txt"',
            'Content-Type: text/plain',
            '',
            content.decode('utf-8'),
            f'--{boundary}--'
        ]
        body = '\r\n'.join(body_parts)
        body_base64 = base64.b64encode(body.encode()).decode()
        
        event = {
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            },
            'body': body_base64,
            'isBase64Encoded': True
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_FILE_FORMAT'
        assert 'CSV or XLSX' in body['error']['message']
    
    @patch('handler.s3_client')
    @patch('handler.FileParser')
    def test_upload_xlsx_file(self, mock_parser_class, mock_s3):
        """Test uploading a valid XLSX file."""
        # Setup mock parser
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parsed_file = MagicMock()
        mock_parsed_file.headers = ['column1', 'column2', 'column3']
        mock_parsed_file.row_count = 10
        mock_parser.parse.return_value = mock_parsed_file
        
        # Create multipart request with XLSX file
        boundary = 'boundary123'
        content = b'PK\x03\x04...'  # Fake XLSX content
        
        body_parts = [
            f'--{boundary}',
            'Content-Disposition: form-data; name="file"; filename="data.xlsx"',
            'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '',
            content.decode('latin-1'),
            f'--{boundary}--'
        ]
        body = '\r\n'.join(body_parts)
        body_base64 = base64.b64encode(body.encode('latin-1')).decode()
        
        event = {
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            },
            'body': body_base64,
            'isBase64Encoded': True
        }
        
        with patch.dict(os.environ, {'DATA_BUCKET': 'test-bucket'}):
            response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['fileType'] == 'xlsx'
        assert body['columns'] == ['column1', 'column2', 'column3']
        assert body['rowCount'] == 10
        
        # Verify S3 key ends with .xlsx
        call_args = mock_s3.put_object.call_args
        assert call_args[1]['Key'].endswith('/input.xlsx')
    
    @patch('handler.s3_client')
    @patch('handler.FileParser')
    def test_s3_upload_failure(self, mock_parser_class, mock_s3):
        """Test handling S3 upload failure."""
        # Setup mock parser
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parsed_file = MagicMock()
        mock_parsed_file.headers = ['name']
        mock_parsed_file.row_count = 1
        mock_parser.parse.return_value = mock_parsed_file
        
        # Make S3 upload fail
        mock_s3.put_object.side_effect = Exception('S3 error')
        
        # Create valid multipart request
        boundary = 'boundary123'
        content = b'name\nJohn'
        
        body_parts = [
            f'--{boundary}',
            'Content-Disposition: form-data; name="file"; filename="test.csv"',
            'Content-Type: text/csv',
            '',
            content.decode('utf-8'),
            f'--{boundary}--'
        ]
        body = '\r\n'.join(body_parts)
        body_base64 = base64.b64encode(body.encode()).decode()
        
        event = {
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            },
            'body': body_base64,
            'isBase64Encoded': True
        }
        
        with patch.dict(os.environ, {'DATA_BUCKET': 'test-bucket'}):
            response = lambda_handler(event, None)
        
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
