#!/bin/bash
# Create IAM user for GitHub Actions deployment

set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

AWS_PROFILE=${AWS_PROFILE:-default}
IAM_USER_NAME="github-actions-deployer"
POLICY_NAME="GitHubActionsDeployPolicy"

echo "==================================="
echo "Create IAM User for GitHub Actions"
echo "==================================="
echo ""
echo "Using AWS profile: $AWS_PROFILE"
echo "IAM User Name: $IAM_USER_NAME"
echo ""

# Check if user already exists
if aws iam get-user --user-name $IAM_USER_NAME --profile $AWS_PROFILE &> /dev/null; then
    echo "⚠️  IAM user '$IAM_USER_NAME' already exists."
    read -p "Do you want to create new access keys for this user? (y/n) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
else
    # Create IAM user
    echo "Creating IAM user: $IAM_USER_NAME"
    aws iam create-user --user-name $IAM_USER_NAME --profile $AWS_PROFILE
    echo "✅ IAM user created"
    echo ""
    
    # Create and attach policy
    echo "Creating IAM policy: $POLICY_NAME"
    POLICY_ARN=$(aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document file://scripts/github-actions-iam-policy.json \
        --profile $AWS_PROFILE \
        --query 'Policy.Arn' \
        --output text)
    
    echo "✅ IAM policy created: $POLICY_ARN"
    echo ""
    
    # Attach policy to user
    echo "Attaching policy to user..."
    aws iam attach-user-policy \
        --user-name $IAM_USER_NAME \
        --policy-arn $POLICY_ARN \
        --profile $AWS_PROFILE
    
    echo "✅ Policy attached to user"
    echo ""
fi

# Create access keys
echo "Creating access keys..."
ACCESS_KEY_OUTPUT=$(aws iam create-access-key \
    --user-name $IAM_USER_NAME \
    --profile $AWS_PROFILE \
    --output json)

AWS_ACCESS_KEY_ID=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.AccessKeyId')
AWS_SECRET_ACCESS_KEY=$(echo $ACCESS_KEY_OUTPUT | jq -r '.AccessKey.SecretAccessKey')

echo ""
echo "✅ Access keys created successfully!"
echo ""
echo "==================================="
echo "IMPORTANT: Save these credentials!"
echo "==================================="
echo ""
echo "AWS_ACCESS_KEY_ID: $AWS_ACCESS_KEY_ID"
echo "AWS_SECRET_ACCESS_KEY: $AWS_SECRET_ACCESS_KEY"
echo ""
echo "⚠️  These credentials will not be shown again!"
echo ""
echo "Next steps:"
echo "1. Save these credentials securely"
echo "2. Run: ./scripts/setup-github-actions.sh"
echo "3. Or manually add them to GitHub:"
echo "   - Go to Settings → Secrets and variables → Actions"
echo "   - Add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
echo ""
