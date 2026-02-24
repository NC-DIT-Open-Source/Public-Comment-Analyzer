# Public Comment Analyzer

A cloud-native AWS application that processes CSV and XLSX files containing public comments and generates AI-powered analysis using AWS Bedrock.

**Live URL**: https://dwah8ht95yiuz.cloudfront.net/

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- AWS CLI configured
- AWS CDK CLI installed

### Setup
1. Copy `.env.example` to `.env` and set your AWS profile:
   ```bash
   cp .env.example .env
   # Edit .env and set AWS_PROFILE=your-profile-name
   ```

2. Deploy everything:
   ```bash
   ./scripts/deploy.sh dev
   ```

### Verify Deployment
```bash
./scripts/verify-deployment.sh dev
```

### Custom Domain Setup
For production deployment with custom domain:
```bash
export CERTIFICATE_ARN=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT_ID
./scripts/deploy-custom-domain.sh
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  CloudFront │────▶│ S3 (Frontend)│     │ API Gateway │
│             │     └──────────────┘     └──────┬──────┘
│             │                                  │
│             │────────────────────────────────▶ │
└─────────────┘                                  │
                                                 ▼
                                    ┌────────────────────┐
                                    │  Lambda Functions  │
                                    │  - Upload Handler  │
                                    │  - Row Processor   │
                                    │  - Aggregator      │
                                    └────────┬───────────┘
                                             │
                        ┌────────────────────┼────────────────────┐
                        ▼                    ▼                    ▼
                   ┌─────────┐         ┌─────────┐         ┌──────────┐
                   │   S3    │         │DynamoDB │         │ Bedrock  │
                   │  Data   │         │  Jobs   │         │  Claude  │
                   └─────────┘         └─────────┘         └──────────┘
```

### Components
- **Frontend**: Angular 17+ with NC DIT Digital Commons Style Guide
- **Backend**: Python Lambda functions (upload, process, analyze)
- **Storage**: S3 for files, DynamoDB for job tracking
- **AI**: AWS Bedrock (Claude Haiku for rows, Claude Opus for aggregates)
- **API**: API Gateway with CORS
- **CDN**: CloudFront with HTTPS

## Project Structure

```
.
├── backend/
│   ├── upload_handler/      # File upload and validation
│   ├── row_processor/       # Row-by-row AI analysis (500 concurrent)
│   ├── aggregate_analyzer/  # Aggregate sentiment analysis
│   └── shared/              # File parser, writer, DynamoDB client
├── frontend/
│   └── public-comment-app/  # Angular application
├── infrastructure/          # AWS CDK (Python)
│   ├── app.py
│   └── stacks/
└── scripts/                 # Deployment and verification scripts
```

## Features

- Upload CSV/XLSX files (up to 100 MB, 50,000 rows)
- Define custom analysis columns with AI instructions
- Concurrent processing (500 rows at a time)
- Real-time progress monitoring
- Download results with original data + AI analysis
- Aggregate sentiment analysis with markdown rendering
- NC DIT branding and style guide compliance

## Development

### Backend Testing
```bash
cd backend/shared
python -m pytest test_*.py -v

cd ../upload_handler
python -m pytest test_handler.py -v

cd ../row_processor
python -m pytest test_handler.py test_error_handling.py -v

cd ../aggregate_analyzer
python -m pytest test_handler.py test_integration.py -v
```

### Frontend Testing
```bash
cd frontend/public-comment-app
npm test
```

### Local Development
```bash
# Backend (with venv)
cd backend/upload_handler
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend/public-comment-app
npm install
npm start  # Runs on http://localhost:4200
```

## Deployment

### Automated Deployment (GitHub Actions)

The project includes automated CI/CD via GitHub Actions. Every push to `main` automatically deploys changes to AWS.

**Setup:**
```bash
# Configure GitHub secrets with your AWS credentials
./scripts/setup-github-actions.sh
```

**Features:**
- Smart change detection (only deploys what changed)
- Automatic testing before deployment
- Separate jobs for backend and frontend
- Manual deployment option via GitHub UI

See `.github/workflows/README.md` for detailed setup instructions.

### Manual Deployment

#### Full Deployment
```bash
./scripts/deploy.sh dev
```

#### Infrastructure Only
```bash
cd infrastructure
source .venv/bin/activate
cdk deploy --context environment=dev --profile $AWS_PROFILE
```

#### Frontend Only
```bash
cd frontend/public-comment-app
npm run build:prod
npm run deploy
```

### Custom Domain Setup
See `CUSTOM_DOMAIN_SETUP.md` for detailed instructions on setting up `commentreviewer.oaip.nc.gov`.

## Security

✅ CORS restricted to specific domain  
✅ File upload validation (size, type, magic bytes)  
✅ Prompt injection protection  
✅ Path traversal prevention  
✅ HTTPS enforced everywhere  
✅ Security headers (HSTS, X-Frame-Options, CSP)  
✅ Private S3 buckets with CloudFront OAI  
✅ Least-privilege IAM roles  
✅ Input sanitization and validation  
✅ Rate limiting (100 req/s, 200 burst)  

## Performance

- **10 rows**: ~15 seconds
- **100 rows**: ~30 seconds
- **1,000 rows**: ~2 minutes
- **5,000 rows**: ~10 minutes

Concurrent processing with 500 workers utilizing AWS Bedrock's 1,000 req/min rate limit.

## Monitoring

```bash
# View Lambda logs
aws logs tail /aws/lambda/PublicCommentAnalyzer-UploadHandler-dev --follow --profile $AWS_PROFILE
aws logs tail /aws/lambda/PublicCommentAnalyzer-RowProcessor-dev --follow --profile $AWS_PROFILE
aws logs tail /aws/lambda/PublicCommentAnalyzer-AggregateAnalyzer-dev --follow --profile $AWS_PROFILE
```

## Troubleshooting

### Frontend shows 403
```bash
cd frontend/public-comment-app
npm run deploy
```

### CORS errors
```bash
cd infrastructure
cdk deploy --context environment=dev --profile $AWS_PROFILE
```

### Processing never completes
Check CloudWatch Logs for Lambda errors and verify Bedrock access in your region.

## Clean Up

```bash
cd infrastructure
cdk destroy --context environment=dev --profile $AWS_PROFILE

# Manually delete S3 buckets and DynamoDB table if needed
```

## Resources

- **Live App**: https://dwah8ht95yiuz.cloudfront.net/
- **Design System**: https://zeroheight.com/6cc837e20/p/638fcb-welcome
- **AWS Account**: 267527030320
- **Region**: us-east-1
- **CloudFront Distribution**: E3C3HXNESHQKVB

## Requirements

Detailed requirements are in `.kiro/specs/public-comment-analyzer/requirements.md`.

## Support

For issues:
1. Check CloudWatch Logs
2. Review `AGENTS.md` for agent-specific guidance
3. Consult AWS service documentation
