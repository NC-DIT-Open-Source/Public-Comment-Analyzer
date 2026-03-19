# GitHub Actions Setup Guide

This guide walks you through setting up automated deployment to AWS via GitHub Actions.

## Overview

Every push to the `main` branch automatically:
1. Detects what changed (backend, frontend, or both)
2. Runs tests
3. Deploys only what changed to AWS
4. Provides deployment summary

## Quick Setup (5 minutes)

### Option A: Use Existing AWS Credentials

If you already have AWS credentials configured locally:

```bash
./scripts/setup-github-actions.sh
```

This will:
- Verify GitHub CLI is installed and authenticated
- Extract AWS credentials from your profile
- Set them as GitHub secrets

### Option B: Create Dedicated IAM User (Recommended)

For better security, create a dedicated IAM user for GitHub Actions:

```bash
# 1. Create IAM user and get credentials
./scripts/create-github-actions-iam-user.sh

# 2. Save the credentials shown (they won't be displayed again!)

# 3. Set up GitHub secrets
./scripts/setup-github-actions.sh
# When prompted, enter the credentials from step 1
```

## Manual Setup

If you prefer to set up manually:

### 1. Create IAM User

1. Go to AWS IAM Console
2. Create user: `github-actions-deployer`
3. Create policy using `scripts/github-actions-iam-policy.json`
4. Attach policy to user
5. Create access keys

### 2. Add GitHub Secrets

1. Go to your GitHub repository
2. Navigate to: Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add two secrets:
   - Name: `AWS_ACCESS_KEY_ID`, Value: `<your-access-key-id>`
   - Name: `AWS_SECRET_ACCESS_KEY`, Value: `<your-secret-access-key>`

## Verify Setup

### 1. Check GitHub Secrets

```bash
gh secret list
```

You should see:
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY

### 2. Test Workflow

```bash
# Trigger manual deployment
gh workflow run deploy.yml -f environment=dev

# Watch the deployment
gh run watch
```

### 3. Check Workflow Status

```bash
# List recent runs
gh run list --workflow=deploy.yml

# View specific run
gh run view <run-id>
```

## How It Works

### Automatic Deployment (Push to Main)

```bash
git add .
git commit -m "Update frontend styling"
git push origin main
```

GitHub Actions will:
1. Detect that only frontend changed
2. Skip backend tests and deployment
3. Run frontend tests
4. Build and deploy frontend to S3
5. Invalidate CloudFront cache

### Manual Deployment

Use the GitHub UI or CLI:

```bash
# Deploy to dev
gh workflow run deploy.yml -f environment=dev

# Deploy to prod
gh workflow run deploy.yml -f environment=prod
```

## Change Detection Logic

The workflow automatically detects changes:

| Changed Files | Actions Taken |
|--------------|---------------|
| `backend/**` or `infrastructure/**` | Deploy CDK stack (backend + infrastructure) |
| `frontend/**` | Build and deploy frontend only |
| Both | Deploy everything |
| Manual trigger | Deploy everything |

## Workflow Jobs

### 1. detect-changes
- Compares current commit with previous
- Outputs which parts changed
- Runs first, determines what other jobs run

### 2. test-backend
- Runs if backend changed
- Tests shared modules
- Tests each Lambda function
- Runs in parallel with other jobs

### 3. test-frontend
- Runs if frontend changed
- Runs Angular unit tests
- Runs in parallel with other jobs

### 4. deploy-infrastructure
- Runs if backend or infrastructure changed
- Installs Python and CDK dependencies
- Copies shared modules to Lambda functions
- Deploys CDK stack
- Outputs CloudFront and S3 bucket info

### 5. deploy-frontend
- Runs if frontend changed
- Installs Node.js dependencies
- Builds Angular app for production
- Uploads to S3
- Invalidates CloudFront cache

### 6. deployment-summary
- Runs after all jobs complete
- Shows what was deployed
- Displays success/failure status

## Troubleshooting

### "Stack does not exist" Error

**Problem:** First deployment fails because stack doesn't exist yet.

**Solution:** Run initial deployment locally:
```bash
./scripts/deploy.sh dev
```

Then future GitHub Actions deployments will work.

### "Access Denied" Errors

**Problem:** IAM user doesn't have required permissions.

**Solution:** 
1. Check IAM policy is attached: `scripts/github-actions-iam-policy.json`
2. Verify all required services are included
3. Check AWS region matches (us-east-1)

### Frontend Build Fails

**Problem:** Missing dependencies or build errors.

**Solution:**
1. Test build locally: `cd frontend && npm run build:prod`
2. Ensure package-lock.json is committed
3. Check Node.js version (should be 18)

### CloudFront Invalidation Fails

**Problem:** Can't invalidate CloudFront cache.

**Solution:**
1. Verify CloudFront distribution exists
2. Check IAM permissions include `cloudfront:CreateInvalidation`
3. Ensure distribution ID is correct

### Tests Fail

**Problem:** Tests fail in CI but pass locally.

**Solution:**
1. Check Python version (3.11)
2. Verify all requirements.txt are up to date
3. Ensure shared modules are copied correctly
4. Check for environment-specific issues

## Monitoring Deployments

### View Logs in GitHub

1. Go to Actions tab
2. Click on workflow run
3. Click on specific job
4. Expand steps to see logs

### View AWS Logs

```bash
# Lambda logs
aws logs tail /aws/lambda/PublicCommentAnalyzer-RowProcessor-dev --follow --profile ncdit

# CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name PublicCommentAnalyzerStack-dev \
  --profile ncdit
```

### Deployment Summary

After each deployment, check the workflow summary:
- Environment deployed to
- What changed
- Deployment status
- CloudFront URL

## Security Best Practices

✅ Use dedicated IAM user for GitHub Actions  
✅ Apply least-privilege IAM policy  
✅ Rotate access keys regularly  
✅ Never commit AWS credentials to repository  
✅ Use GitHub Secrets for sensitive data  
✅ Enable MFA on AWS accounts  
✅ Review CloudFormation changes before deployment  
✅ Monitor CloudWatch for unusual activity  

## Cost Optimization

- Workflows only run on `main` branch pushes
- Tests run in parallel to save time
- Only changed components are deployed
- Uses GitHub-hosted runners (free for public repos)

## Advanced Usage

### Deploy to Multiple Environments

```bash
# Deploy to dev
gh workflow run deploy.yml -f environment=dev

# Deploy to prod
gh workflow run deploy.yml -f environment=prod
```

### Skip CI for Commits

Add `[skip ci]` to commit message:
```bash
git commit -m "Update README [skip ci]"
```

### Re-run Failed Deployment

```bash
# List recent runs
gh run list --workflow=deploy.yml

# Re-run specific run
gh run rerun <run-id>
```

### View Workflow File

```bash
cat .github/workflows/deploy.yml
```

## Support

### GitHub Actions Issues
- Check workflow logs in Actions tab
- Review `.github/workflows/deploy.yml`
- Verify GitHub secrets are set

### AWS Deployment Issues
- Check CloudFormation console
- Review Lambda logs in CloudWatch
- Verify IAM permissions

### Need Help?
1. Check workflow logs
2. Review this guide
3. Check `AGENTS.md` for project-specific guidance
4. Review AWS service documentation

## Next Steps

After setup:
1. ✅ Make a small change to test deployment
2. ✅ Watch the workflow run in GitHub Actions
3. ✅ Verify deployment in AWS Console
4. ✅ Check the deployed application works

## Useful Commands

```bash
# Setup
./scripts/setup-github-actions.sh

# Create IAM user
./scripts/create-github-actions-iam-user.sh

# List secrets
gh secret list

# Trigger deployment
gh workflow run deploy.yml -f environment=dev

# Watch deployment
gh run watch

# List runs
gh run list --workflow=deploy.yml

# View run details
gh run view <run-id>

# View logs
gh run view <run-id> --log

# Re-run failed
gh run rerun <run-id>
```

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [GitHub CLI Documentation](https://cli.github.com/)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
