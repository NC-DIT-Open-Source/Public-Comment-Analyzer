# GitHub Actions Setup Checklist

Follow these steps to enable automated deployment:

## ✅ Step 1: Code is Ready
- [x] GitHub Actions workflow created (`.github/workflows/deploy.yml`)
- [x] Setup scripts created
- [x] Documentation written
- [x] Changes committed to main branch

## ⏳ Step 2: Configure GitHub Secrets

You need to add AWS credentials as GitHub secrets. Choose one option:

### Option A: Automated Setup (Recommended)
```bash
./scripts/setup-github-actions.sh
```

This script will:
1. Check if GitHub CLI is installed and authenticated
2. Extract AWS credentials from your profile
3. Automatically set them as GitHub secrets

### Option B: Create Dedicated IAM User (Most Secure)
```bash
# 1. Create IAM user with proper permissions
./scripts/create-github-actions-iam-user.sh

# 2. Save the credentials shown (won't be displayed again!)

# 3. Set up GitHub secrets with those credentials
./scripts/setup-github-actions.sh
```

### Option C: Manual Setup
1. Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions
2. Click "New repository secret"
3. Add these two secrets:
   - `AWS_ACCESS_KEY_ID`: Your AWS access key
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret key

## ⏳ Step 3: Verify Secrets Are Set

```bash
gh secret list
```

You should see:
```
AWS_ACCESS_KEY_ID       Updated YYYY-MM-DD
AWS_SECRET_ACCESS_KEY   Updated YYYY-MM-DD
```

## ⏳ Step 4: Push to Main Branch

```bash
git push origin main
```

This will trigger the first automated deployment!

## ⏳ Step 5: Watch the Deployment

### In GitHub UI:
1. Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/actions
2. Click on the running workflow
3. Watch the progress

### In Terminal:
```bash
gh run watch
```

## ⏳ Step 6: Verify Deployment

After the workflow completes:

```bash
# Check the deployed application
./scripts/verify-deployment.sh dev

# Or manually check CloudFront URL
aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-dev \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text \
  --profile ncdit
```

## Troubleshooting

### If Step 2 Fails (Can't Get Credentials)
Your AWS profile might be using SSO or temporary credentials. You need to:
1. Create a dedicated IAM user for GitHub Actions
2. Use `./scripts/create-github-actions-iam-user.sh` to create it
3. Or manually create one in AWS IAM Console

### If Step 4 Fails (First Deployment)
The first deployment might fail if the stack doesn't exist yet. Run:
```bash
./scripts/deploy.sh dev
```
Then future GitHub Actions deployments will work.

### If Tests Fail
Check the workflow logs to see which tests failed:
```bash
gh run view --log
```

## Next Steps

Once setup is complete:
- ✅ Every push to `main` automatically deploys
- ✅ Only changed components are deployed (smart detection)
- ✅ Tests run before deployment
- ✅ Deployment summaries in GitHub Actions

## Quick Reference

```bash
# Setup secrets
./scripts/setup-github-actions.sh

# Trigger manual deployment
gh workflow run deploy.yml -f environment=dev

# Watch deployment
gh run watch

# List recent runs
gh run list --workflow=deploy.yml

# View specific run
gh run view <run-id> --log
```

## Documentation

- Full setup guide: `GITHUB_ACTIONS_SETUP.md`
- Workflow details: `.github/workflows/README.md`
- Project guide: `AGENTS.md`
