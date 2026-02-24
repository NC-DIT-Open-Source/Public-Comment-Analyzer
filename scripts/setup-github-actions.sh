#!/bin/bash
# Setup script for GitHub Actions deployment

set -e

echo "==================================="
echo "GitHub Actions Setup for AWS Deploy"
echo "==================================="
echo ""

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

AWS_PROFILE=${AWS_PROFILE:-default}

echo "Using AWS profile: $AWS_PROFILE"
echo ""

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    echo ""
    echo "Or use Homebrew: brew install gh"
    exit 1
fi

# Check if user is authenticated with GitHub
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI."
    echo "Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is installed and authenticated"
echo ""

# Get AWS credentials
echo "Fetching AWS credentials for profile: $AWS_PROFILE"
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile $AWS_PROFILE 2>/dev/null || echo "")
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile $AWS_PROFILE 2>/dev/null || echo "")

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "⚠️  Could not find static AWS credentials for profile: $AWS_PROFILE"
    echo ""
    echo "This profile may be using SSO or temporary credentials."
    echo "For GitHub Actions, you need to create a dedicated IAM user with static credentials."
    echo ""
    echo "Steps to create IAM user for GitHub Actions:"
    echo "1. Go to AWS IAM Console"
    echo "2. Create a new IAM user (e.g., 'github-actions-deployer')"
    echo "3. Attach the policy from: scripts/github-actions-iam-policy.json"
    echo "4. Create access keys for the user"
    echo "5. Run this script again with those credentials"
    echo ""
    read -p "Do you want to manually enter AWS credentials? (y/n) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
    
    echo ""
    read -p "Enter AWS Access Key ID: " AWS_ACCESS_KEY_ID
    read -sp "Enter AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
    echo ""
    echo ""
fi

echo "✅ AWS credentials ready"
echo ""

# Confirm before setting secrets
echo "⚠️  This will set the following GitHub secrets:"
echo "   - AWS_ACCESS_KEY_ID"
echo "   - AWS_SECRET_ACCESS_KEY"
echo ""
echo "These secrets will be used by GitHub Actions to deploy to AWS."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Set GitHub secrets
echo "Setting GitHub secrets..."
echo "$AWS_ACCESS_KEY_ID" | gh secret set AWS_ACCESS_KEY_ID
echo "$AWS_SECRET_ACCESS_KEY" | gh secret set AWS_SECRET_ACCESS_KEY

echo ""
echo "✅ GitHub secrets configured successfully!"
echo ""
echo "Next steps:"
echo "1. Commit and push your changes to the main branch"
echo "2. Go to GitHub Actions tab to watch the deployment"
echo "3. Or manually trigger a deployment:"
echo "   gh workflow run deploy.yml -f environment=dev"
echo ""
echo "To view workflow runs:"
echo "   gh run list --workflow=deploy.yml"
echo ""
echo "To watch a specific run:"
echo "   gh run watch"
echo ""
