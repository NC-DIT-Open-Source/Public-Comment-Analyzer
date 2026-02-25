"""Lambda handler for file upload and validation."""

import json
import os
import re
import base64
import uuid
import tempfile
from typing import Dict, Any
import boto3

# Import from shared module (assuming it's in the Lambda layer or copied to the package)
try:
    from file_parser import FileParser
except ImportError:
    # If running locally or shared module not in layer, try relative import
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
    from file_parser import FileParser

s3_client = boto3.client('s3')

# Maximum upload size: 100 MB
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

# Maximum number of rows to prevent abuse
MAX_ROW_COUNT = 50_000

# CSV magic bytes: no reliable magic, but XLSX has a known signature
XLSX_MAGIC_BYTES = b'PK\x03\x04'


def _cors_origin() -> str:
    """Return the allowed CORS origin from environment, falling back to '*'."""
    return os.environ.get('ALLOWED_ORIGIN') or '*'


def get_data_bucket():
    """Get the data bucket name from environment."""
    return os.environ.get('DATA_BUCKET', '')


def parse_multipart_form_data(body: str, content_type: str) -> Dict[str, Any]:
    """
    Parse multipart/form-data from API Gateway event.
    
    Args:
        body: Base64 encoded body from API Gateway
        content_type: Content-Type header value
        
    Returns:
        Dictionary with 'file' (bytes) and 'filename' (str)
    """
    # Extract boundary from content type
    boundary = None
    for part in content_type.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part.split('=', 1)[1]
            break
    
    if not boundary:
        raise ValueError("No boundary found in Content-Type header")
    
    # Decode body
    body_bytes = base64.b64decode(body)
    
    # Split by boundary
    boundary_bytes = f'--{boundary}'.encode()
    parts = body_bytes.split(boundary_bytes)
    
    # Find the file part
    for part in parts:
        if b'Content-Disposition' in part and b'filename=' in part:
            # Extract filename
            lines = part.split(b'\r\n')
            filename = None
            content_start = 0
            
            for i, line in enumerate(lines):
                if b'filename=' in line:
                    # Extract filename from Content-Disposition header
                    line_str = line.decode('utf-8', errors='ignore')
                    for segment in line_str.split(';'):
                        segment = segment.strip()
                        if segment.startswith('filename='):
                            filename = segment.split('=', 1)[1].strip('"')
                            break
                
                # Find where content starts (after empty line)
                if line == b'' and i > 0:
                    content_start = i + 1
                    break
            
            if filename:
                # Extract file content (everything after headers until end)
                file_content = b'\r\n'.join(lines[content_start:])
                # Remove trailing boundary markers
                if file_content.endswith(b'\r\n'):
                    file_content = file_content[:-2]
                
                return {
                    'file': file_content,
                    'filename': filename
                }
    
    raise ValueError("No file found in multipart data")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and injection attacks.
    
    Strips directory components, removes dangerous characters, and limits length.
    """
    # Strip any directory path components (prevents path traversal like ../../etc/passwd)
    filename = os.path.basename(filename)
    # Remove null bytes
    filename = filename.replace('\x00', '')
    # Only allow alphanumeric, dots, hyphens, underscores, and spaces
    filename = re.sub(r'[^\w.\-\s]', '_', filename)
    # Collapse multiple dots (prevents extension confusion like file...csv)
    filename = re.sub(r'\.{2,}', '.', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    if '.' in filename:
        return filename.rsplit('.', 1)[1].lower()
    return ''


def validate_file_format(extension: str) -> bool:
    """Validate that file format is CSV or XLSX."""
    return extension in ['csv', 'xlsx', 'xls']


def validate_file_content(file_content: bytes, extension: str) -> bool:
    """
    Validate file content matches the claimed extension by checking magic bytes.
    
    Returns True if the content appears valid for the given extension.
    """
    if extension in ['xlsx', 'xls']:
        # XLSX files are ZIP archives — must start with PK signature
        return file_content[:4] == XLSX_MAGIC_BYTES
    elif extension == 'csv':
        # CSV: ensure it's decodable text (not a binary file masquerading as CSV)
        try:
            sample = file_content[:8192]
            sample.decode('utf-8')
            return True
        except UnicodeDecodeError:
            try:
                sample.decode('latin-1')
                return True
            except UnicodeDecodeError:
                return False
    return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle file upload requests.
    
    Args:
        event: API Gateway event with multipart file upload
        context: Lambda context
        
    Returns:
        Response with file metadata or error
    """
    print("=== UPLOAD HANDLER START ===")
    print(f"Event keys: {list(event.keys())}")
    print(f"Request ID: {context.aws_request_id}")
    
    try:
        # Extract content type and body
        headers = event.get('headers', {})
        print(f"Headers: {headers}")
        
        content_type = headers.get('content-type') or headers.get('Content-Type', '')
        print(f"Content-Type: {content_type}")
        
        if not content_type.startswith('multipart/form-data'):
            print("ERROR: Invalid content type")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'INVALID_CONTENT_TYPE',
                        'message': 'Request must be multipart/form-data'
                    }
                })
            }
        
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        print(f"Body length: {len(body)}, Is Base64: {is_base64}")
        
        if not is_base64:
            # If not base64 encoded, encode it
            body = base64.b64encode(body.encode()).decode()
            print("Encoded body to base64")
        
        # Parse multipart data
        print("Parsing multipart data...")
        try:
            file_data = parse_multipart_form_data(body, content_type)
            print(f"Parsed file: {file_data['filename']}, size: {len(file_data['file'])} bytes")
        except Exception as e:
            print(f"ERROR parsing multipart data: {str(e)}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'INVALID_MULTIPART_DATA',
                        'message': f'Failed to parse multipart data: {str(e)}'
                    }
                })
            }
        
        filename = sanitize_filename(file_data['filename'])
        file_content = file_data['file']
        
        # Enforce file size limit
        if len(file_content) > MAX_FILE_SIZE_BYTES:
            print(f"ERROR: File too large: {len(file_content)} bytes")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'FILE_TOO_LARGE',
                        'message': f'File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB'
                    }
                })
            }
        
        # Validate file format by extension
        extension = get_file_extension(filename)
        print(f"File extension: {extension}")
        
        if not validate_file_format(extension):
            print(f"ERROR: Invalid file format: {extension}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'INVALID_FILE_FORMAT',
                        'message': 'File must be in CSV or XLSX format'
                    }
                })
            }
        
        # Validate file content matches claimed type (magic byte check)
        if not validate_file_content(file_content, extension):
            print(f"ERROR: File content does not match extension: {extension}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'INVALID_FILE_CONTENT',
                        'message': 'File content does not match the expected format'
                    }
                })
            }
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        print(f"Generated file ID: {file_id}")
        
        # Save file to temporary location for parsing
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        print(f"Saved to temp file: {tmp_file_path}")
        
        try:
            # Parse file to extract headers and row count
            print("Parsing file...")
            parser = FileParser()
            parsed_file = parser.parse(tmp_file_path, extension)
            print(f"Parsed: {len(parsed_file.headers)} columns, {parsed_file.row_count} rows")
            
            # Enforce row count limit
            if parsed_file.row_count > MAX_ROW_COUNT:
                print(f"ERROR: Too many rows: {parsed_file.row_count}")
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': _cors_origin()
                    },
                    'body': json.dumps({
                        'error': {
                            'code': 'TOO_MANY_ROWS',
                            'message': f'File exceeds maximum of {MAX_ROW_COUNT:,} rows'
                        }
                    })
                }
            
            # Store file in S3
            s3_key = f'uploads/{file_id}/input.{extension}'
            bucket = get_data_bucket()
            print(f"Uploading to S3: {bucket}/{s3_key}")
            
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=file_content,
                ContentType='application/octet-stream',
                Metadata={
                    'file-id': file_id
                }
            )
            print("S3 upload complete")
            
            # Return file metadata
            response_body = {
                'fileId': file_id,
                'columns': parsed_file.headers,
                'rowCount': parsed_file.row_count,
                'filename': filename,
                'fileType': extension,
                'version': '1.1.0',
                'deployedVia': 'GitHub Actions CI/CD'
            }
            print(f"Returning success response: {response_body}")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps(response_body)
            }
            
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)
                print(f"Cleaned up temp file")
    
    except Exception as e:
        # Log detailed error information
        error_type = type(e).__name__
        error_message = str(e)
        
        print(f"ERROR: Upload processing failed")
        print(f"  Error type: {error_type}")
        print(f"  Error message: {error_message}")
        
        import traceback
        print(f"  Stack trace:")
        traceback.print_exc()
        
        # Provide user-friendly error message based on error type
        if 'encoding' in error_message.lower() or 'decode' in error_message.lower():
            user_message = 'File encoding is not supported. Please ensure the file is UTF-8 or Latin-1 encoded.'
        elif 'parse' in error_message.lower() or 'invalid' in error_message.lower():
            user_message = 'File format is invalid or corrupted. Please check the file and try again.'
        else:
            user_message = 'An error occurred while processing the upload. Please try again or contact support if the issue persists.'
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': _cors_origin()
            },
            'body': json.dumps({
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': user_message
                }
            })
        }
