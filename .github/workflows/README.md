# GitHub Actions CI/CD

This directory contains GitHub Actions workflows for automated deployment to AWS.

## Workflows

### deploy.yml
Automatically deploys the application to AWS when changes are pushed to the `main` branch.

**Features:**
- Smart change detection (only deploys what changed)
- Separate jobs for backend and frontend
- Runs tests before deployment
- Supports manual deployment via workflow_dispatch
- Deployment summaries in GitHub Actions UI

**Change Detection:**
- Backend changes: `backend/` or `infrastructure/` directories
- Frontend changes: `frontend/` directory
- Manual trigger: deploys everything

## Setup Instructions

### 1. Configure AWS Credentials

Add the following secrets to your GitHub repository:
- Go to Settings → Secrets and variables → Actions
- Add these repository secrets:

```
AWS_ACCESS_KEY_ID: Your AWS access key
AWS_SECRET_ACCESS_KEY: Your AWS secret key
```

**Best Practice:** Create a dedicated IAM user for GitHub Actions with minimal required permissions.

### 2. Required IAM Permissions

The IAM user needs permissions for:
- CloudFormation (create/update/delete stacks)
- Lambda (create/update functions)
- S3 (create buckets, upload files)
- DynamoDB (create tables)
- CloudFront (create distributions, invalidate cache)
- IAM (create roles for Lambda functions)
- API Gateway (create APIs)
- Bedrock (invoke models)

Example IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "s3:*",
        "dynamodb:*",
        "cloudfront:*",
        "iam:*",
        "apigateway:*",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Verify Setup

1. Push a change to the `main` branch
2. Go to Actions tab in GitHub
3. Watch the workflow run
4. Check deployment summary

### 4. Manual Deployment

You can manually trigger a deployment:
1. Go to Actions tab
2. Select "Deploy to AWS" workflow
3. Click "Run workflow"
4. Choose environment (dev/prod)
5. Click "Run workflow"

## Workflow Behavior

### On Push to Main
- Detects which parts of the codebase changed
- Runs relevant tests
- Deploys only what changed:
  - Backend/Infrastructure changes → Deploy CDK stack
  - Frontend changes → Build and deploy to S3/CloudFront
  - Both changed → Deploy everything

### On Manual Trigger
- Deploys everything regardless of changes
- Useful for:
  - Initial deployment
  - Fixing deployment issues
  - Deploying to different environments

## Troubleshooting

### Deployment Fails with "Stack does not exist"
- Run a manual deployment first to create the initial stack:
  `cd infrastructure && cdk deploy --context environment=dev --profile $AWS_PROFILE`

### CloudFront Invalidation Fails
- Check that the CloudFront distribution exists
- Verify AWS credentials have CloudFront permissions

### Frontend Build Fails
- Check Node.js version (should be 22)
- Verify package-lock.json is committed
- Check for missing dependencies

### Backend Tests Fail
- Check Python version (should be 3.12)
- Verify all requirements.txt files are up to date
- Check that shared modules are copied correctly

## Environment Variables

The workflow uses these environment variables:
- `AWS_REGION`: us-east-1 (default)
- `ENVIRONMENT`: dev (default) or prod
- `NODE_VERSION`: 22
- `PYTHON_VERSION`: 3.12

## Deployment Outputs

After successful deployment, check the workflow summary for:
- CloudFront URL
- S3 bucket names
- Deployment status for each component

## Security Notes

- Never commit AWS credentials to the repository
- Use GitHub Secrets for sensitive data
- Rotate AWS access keys regularly
- Use least-privilege IAM policies
- Enable MFA on AWS accounts
- Review CloudFormation changes before deployment

## Cost Optimization

- Workflows run only on changes to `main` branch
- Tests run in parallel to save time
- Frontend deployment skipped if no changes
- Backend deployment skipped if no changes

## Monitoring

Monitor deployments:
- GitHub Actions logs
- AWS CloudFormation console
- AWS Lambda logs (CloudWatch)
- CloudFront access logs

## Support

For issues with:
- Workflow configuration: Check this README
- AWS permissions: Review IAM policies
- Deployment failures: Check CloudFormation events
- Application errors: Check Lambda logs in CloudWatch
