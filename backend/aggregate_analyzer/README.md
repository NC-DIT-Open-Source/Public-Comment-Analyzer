# Aggregate Analyzer Lambda Function

This Lambda function generates aggregate sentiment analysis using Claude Opus 4.6 for the Public Comment Analyzer application.

## Overview

The aggregate analyzer reads processed comment data from S3, formats it for analysis, and uses AWS Bedrock with Claude Opus 4.6 to generate comprehensive aggregate insights including sentiment distribution, key themes, and quantitative summaries.

## Requirements

This function implements the following requirements:
- **6.1**: Send complete processed data to AWS Bedrock with Claude Opus 4.6
- **6.2**: Request summary analysis including sentiment distribution and key themes
- **6.3**: Display aggregate analysis to user in readable format
- **6.5**: Allow users to download or copy aggregate analysis text
- **7.2**: Use AWS Bedrock for all AI model access
- **7.4**: Use Claude Opus 4.6 for aggregate analysis

## API

### Endpoint
`GET /api/results/{jobId}`

### Request
Path parameter:
- `jobId`: The job ID from the processing job

### Response
Success (200):
```json
{
  "downloadUrl": "https://s3.amazonaws.com/presigned-url",
  "aggregateAnalysis": "Aggregate analysis text..."
}
```

Error responses:
- 400: Missing jobId or job not completed
- 404: Job not found
- 500: AWS service error or analysis error

## Implementation Details

### Data Formatting
The function formats processed data for analysis by:
1. Calculating value distributions for each analysis column
2. Computing percentages for each value
3. Including sample rows (first 5 and last 5)
4. Limiting output to top 10 values per column

### Prompt Construction
The prompt requests:
1. Overall sentiment distribution with percentages
2. Key themes and patterns
3. Notable trends or outliers
4. Quantitative summary statistics

### Bedrock Integration
- Model: `anthropic.claude-opus-4-20250514`
- Max tokens: 2000
- Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)

### Caching
The function caches aggregate analysis in DynamoDB to avoid redundant Bedrock calls for the same job.

### Presigned URLs
Generated S3 presigned URLs expire after 1 hour (3600 seconds).

## Environment Variables

- `DATA_BUCKET`: S3 bucket name for data storage
- `JOBS_TABLE`: DynamoDB table name for job tracking

## Dependencies

- boto3: AWS SDK for Python
- chardet: Character encoding detection
- openpyxl: XLSX file parsing

## Testing

Run unit tests:
```bash
python -m pytest test_handler.py -v
```

Run integration tests:
```bash
python -m pytest test_integration.py -v
```

Run all tests:
```bash
python -m pytest test_*.py -v
```

## Deployment

1. Copy shared modules:
```bash
./copy_shared.sh
```

2. Deploy with CDK:
```bash
cd ../../infrastructure
cdk deploy
```

## Error Handling

The function implements comprehensive error handling:
- Missing or invalid jobId
- Job not found in DynamoDB
- Job not yet completed
- S3 download failures
- Bedrock API failures (with retry logic)
- File parsing errors

All errors return user-friendly messages with appropriate HTTP status codes.
