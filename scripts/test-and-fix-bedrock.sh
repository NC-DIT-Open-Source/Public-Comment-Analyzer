#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# Use AWS_PROFILE from environment or default to 'default'
AWS_PROFILE=${AWS_PROFILE:-default}
REGION="us-east-1"

echo "=== Testing Bedrock Access and Fixing IAM ==="
echo ""

# Test if AWS session is valid
echo "1. Checking AWS session..."
if ! aws sts get-caller-identity --profile $AWS_PROFILE &>/dev/null; then
    echo "❌ AWS session expired. Please run: aws sso login --profile $AWS_PROFILE"
    exit 1
fi
echo "✓ AWS session is valid"
echo ""

# Get the Lambda execution role name
echo "2. Getting Lambda execution role..."
ROLE_NAME=$(aws iam list-roles --profile $AWS_PROFILE --query 'Roles[?contains(RoleName, `PublicCommentAnalyzerStac-LambdaExecutionRole`)].RoleName' --output text)
if [ -z "$ROLE_NAME" ]; then
    echo "❌ Could not find Lambda execution role"
    exit 1
fi
echo "✓ Found role: $ROLE_NAME"
echo ""

# Get current policy
echo "3. Checking current IAM policy..."
POLICY_NAME="LambdaExecutionRoleDefaultPolicy6D69732F"
aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" --profile $AWS_PROFILE --output json | jq '.PolicyDocument.Statement[] | select(.Action | type == "array" and contains(["bedrock:InvokeModel"]))'
echo ""

# Test Bedrock access with Python
echo "4. Testing Bedrock model access..."
python3 test_bedrock_access.py
echo ""

echo "=== Test Complete ==="
