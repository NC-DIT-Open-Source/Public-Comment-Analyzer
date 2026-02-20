# Upload Handler Lambda Function

This Lambda function handles file uploads for the Public Comment Analyzer application.

## Features

- Accepts multipart/form-data file uploads from API Gateway
- Validates file format (CSV or XLSX only)
- Parses files to extract headers and row count
- Generates unique file IDs (UUID)
- Stores files in S3 at `uploads/{fileId}/input.{ext}`
- Returns file metadata (fileId, columns, rowCount, filename, fileType)

## API

### Request

- **Method**: POST
- **Content-Type**: multipart/form-data
- **Body**: File upload with field name "file"

### Response

**Success (200)**:
```json
{
  "fileId": "uuid-string",
  "columns": ["column1", "column2", ...],
  "rowCount": 123,
  "filename": "original-filename.csv",
  "fileType": "csv"
}
```

**Error (400 - Invalid Format)**:
```json
{
  "error": {
    "code": "INVALID_FILE_FORMAT",
    "message": "File must be in CSV or XLSX format",
    "details": "Received file with extension: txt"
  }
}
```

**Error (500 - Internal Error)**:
```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An error occurred while processing the upload",
    "details": "Error details..."
  }
}
```

## Environment Variables

- `DATA_BUCKET`: S3 bucket name for storing uploaded files
- `JOBS_TABLE`: DynamoDB table name for job tracking (not used in this handler)
- `ENVIRONMENT`: Environment name (dev, staging, prod)

## Dependencies

- boto3: AWS SDK for S3 operations
- openpyxl: XLSX file parsing
- chardet: Character encoding detection for CSV files

## Deployment

Before deploying, run the copy script to include shared modules:

```bash
bash copy_shared.sh
```

This copies the `file_parser.py` module from the shared directory into the upload_handler directory so it's included in the Lambda deployment package.

## Testing

Run unit tests:

```bash
python -m pytest test_handler.py -v
```

All tests should pass before deployment.

## Requirements Validated

This implementation validates the following requirements:

- **1.1**: Validates file format (CSV or XLSX)
- **1.2**: Preserves all original columns and data (via FileParser)
- **1.3**: Returns descriptive error for invalid formats
- **1.4**: Displays column headers to user (returns in response)
- **1.5**: Supports files with at least 10,000 rows (no artificial limits)
