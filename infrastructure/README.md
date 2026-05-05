# Infrastructure

AWS CDK infrastructure for Public Comment Analyzer.

## Prerequisites

- Python 3.12+
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed: `npm install -g aws-cdk`

## Setup

1. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Bootstrap CDK (first time only):
```bash
cdk bootstrap
```

## Deployment

### Deploy to dev environment

```bash
cdk deploy --context environment=dev
```

### Deploy to prod environment

```bash
cdk deploy --context environment=prod
```

### Specify AWS account and region

```bash
cdk deploy --context account=123456789012 --context region=us-west-2
```

## Infrastructure Components

### S3 Buckets

- **Data Bucket**: Stores uploaded files and processed results
  - Lifecycle policy: Files deleted after 7 days
  - Encryption: S3-managed
  - CORS enabled for frontend access

- **Frontend Bucket**: Hosts Angular static website
  - Encryption: S3-managed
  - Accessed via CloudFront only

### DynamoDB Table

- **Jobs Table**: Tracks processing job status
  - Partition key: `jobId`
  - Billing: Pay-per-request
  - TTL enabled for automatic cleanup
  - Point-in-time recovery enabled

### Lambda Functions

- **Upload Handler**: Validates and stores uploaded files
  - Runtime: Python 3.12
  - Timeout: 30 seconds
  - Memory: 512 MB

- **Row Processor**: Processes comments using Bedrock
  - Runtime: Python 3.12
  - Timeout: 15 minutes
  - Memory: 1024 MB
  - Reserved concurrency: 10

- **Aggregate Analyzer**: Generates sentiment analysis
  - Runtime: Python 3.12
  - Timeout: 5 minutes
  - Memory: 512 MB

- **Status Handler**: Returns job status from DynamoDB
  - Runtime: Python 3.12
  - Timeout: 10 seconds

### API Gateway

REST API with endpoints:
- `POST /api/upload` - Upload file
- `POST /api/process` - Start processing
- `GET /api/status/{jobId}` - Get job status
- `GET /api/results/{jobId}` - Get results

CORS enabled for frontend access.

### CloudFront Distribution

- Default behavior: Serves frontend from S3
- `/api/*` behavior: Proxies to API Gateway
- HTTPS only
- SPA routing support (404 → index.html)

### IAM Roles

Lambda execution role with permissions for:
- CloudWatch Logs
- S3 read/write (data bucket)
- DynamoDB read/write
- Bedrock InvokeModel (Claude Haiku and Opus)

## Resource Tagging

All resources are tagged with:
- `Application`: PublicCommentAnalyzer
- `Environment`: dev/prod
- `ManagedBy`: CDK

## Useful Commands

- `cdk ls` - List all stacks
- `cdk synth` - Synthesize CloudFormation template
- `cdk diff` - Compare deployed stack with current state
- `cdk deploy` - Deploy stack
- `cdk destroy` - Remove stack

## Outputs

After deployment, the stack outputs:
- Data bucket name
- Frontend bucket name
- Jobs table name
- API Gateway URL
- CloudFront distribution URL
