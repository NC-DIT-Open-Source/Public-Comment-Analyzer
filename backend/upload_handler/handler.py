"""Lambda handler for file upload and validation."""

import json
import os
import re
import base64
import uuid
import tempfile
import logging
import traceback
from typing import Dict, Any
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Shared modules are provided via Lambda Layer (/opt/python/) at runtime.
# For local testing, fall back to the sibling shared/ directory.
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from file_parser import FileParser
from auth import validate_access_key, build_unauthorized_response

s3_client = boto3.client('s3')

# Maximum upload size: 100 MB
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024

# Maximum number of rows to prevent abuse
MAX_ROW_COUNT = 50_000

# CSV magic bytes: no reliable magic, but XLSX has a known signature
XLSX_MAGIC_BYTES = b'PK\x03\x04'


def _log_safe(value, max_len: int = 200) -> str:
    """Neutralize user-supplied values before logging (Log Forging): strip
    CR/LF so a crafted value can't fabricate log lines, and cap length."""
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    return text[:max_len]


def _cors_origin() -> str:
    """Return the allowed CORS origin from environment.

    Fails closed (empty string) if ALLOWED_ORIGIN is unset so the browser
    rejects the response — mirrors validate_access_key, which fails closed
    when no auth secret is configured.
    """
    origin = os.environ.get('ALLOWED_ORIGIN')
    if not origin:
        logger.error("ALLOWED_ORIGIN is not set; CORS will fail closed")
        return ''
    return origin


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


# Canonical extensions: S3 keys are always built from this mapping's values,
# never the user-supplied filename, so user input can't choose the write path
# (Checkmarx Unrestricted Write S3).
CANONICAL_EXTENSIONS = {'csv': 'csv', 'xlsx': 'xlsx', 'xls': 'xls'}


def validate_file_format(extension: str) -> bool:
    """Validate that file format is CSV or XLSX."""
    return extension in CANONICAL_EXTENSIONS


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
    logger.info("=== UPLOAD HANDLER START ===")
    logger.info(f"Event keys: {list(event.keys())}")
    logger.info(f"Request ID: {getattr(context, 'aws_request_id', 'N/A')}")

    # Validate access key
    if not validate_access_key(event):
        return build_unauthorized_response(_cors_origin())
    
    try:
        # Extract content type and body. Never log the headers dict — it carries
        # the X-Access-Key credential (and is user input; Log Forging).
        headers = event.get('headers', {})

        content_type = headers.get('content-type') or headers.get('Content-Type', '')
        logger.info(f"Content-Type: {_log_safe(content_type)}")
        
        if not content_type.startswith('multipart/form-data'):
            logger.error("Invalid content type")
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
        logger.info(f"Body length: {len(body)}, Is Base64: {is_base64}")
        
        if not is_base64:
            # If not base64 encoded, encode it
            body = base64.b64encode(body.encode()).decode()
            logger.debug("Encoded body to base64")
        
        # Parse multipart data
        logger.info("Parsing multipart data...")
        try:
            file_data = parse_multipart_form_data(body, content_type)
            logger.info(f"Parsed file: {_log_safe(file_data['filename'])}, size: {len(file_data['file'])} bytes")
        except Exception as e:
            # Log the detail; return only a generic message (Information
            # Exposure Through an Error Message).
            logger.error(f"Error parsing multipart data: {str(e)}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': _cors_origin()
                },
                'body': json.dumps({
                    'error': {
                        'code': 'INVALID_MULTIPART_DATA',
                        'message': 'The uploaded form data could not be parsed. Please re-upload the file.'
                    }
                })
            }
        
        filename = sanitize_filename(file_data['filename'])
        file_content = file_data['file']
        
        # Enforce file size limit
        if len(file_content) > MAX_FILE_SIZE_BYTES:
            logger.warning(f"File too large: {len(file_content)} bytes")
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
        logger.info(f"File extension: {_log_safe(extension, 20)}")

        if not validate_file_format(extension):
            logger.warning(f"Invalid file format: {_log_safe(extension, 20)}")
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
            logger.warning(f"File content does not match extension: {extension}")
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
        
        # From here on use only the canonical extension (fixed allow-list value),
        # so the temp-file suffix and S3 key never contain user-controlled text.
        extension = CANONICAL_EXTENSIONS[extension]

        # Generate unique file ID
        file_id = str(uuid.uuid4())
        logger.info(f"Generated file ID: {file_id}")

        # Save file to temporary location for parsing
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        logger.debug(f"Saved to temp file: {tmp_file_path}")
        
        try:
            # Parse file to extract headers and row count
            logger.info("Parsing file...")
            parser = FileParser()
            parsed_file = parser.parse(tmp_file_path, extension)
            logger.info(f"Parsed: {len(parsed_file.headers)} columns, {parsed_file.row_count} rows")
            
            # Enforce row count limit
            if parsed_file.row_count > MAX_ROW_COUNT:
                logger.warning(f"Too many rows: {parsed_file.row_count}")
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
            logger.info(f"Uploading to S3: {bucket}/{s3_key}")
            
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=file_content,
                ContentType='application/octet-stream',
                Metadata={
                    'file-id': file_id
                }
            )
            logger.info("S3 upload complete")
            
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
            logger.info(f"Upload succeeded: fileId={file_id}, rows={parsed_file.row_count}, cols={len(parsed_file.headers)}")
            
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
                logger.debug("Cleaned up temp file")
    
    except Exception as e:
        # Log detailed error information
        error_type = type(e).__name__
        error_message = str(e)
        
        logger.error("Upload processing failed")
        logger.error(f"Error type: {error_type}")
        logger.error(f"Error message: {error_message}")
        logger.error("Stack trace:", exc_info=True)
        
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
