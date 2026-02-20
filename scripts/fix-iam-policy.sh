#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# Use AWS_PROFILE from environment or default to 'default'
AWS_PROFILE=${AWS_PROFILE:-default}

echo "=== Fixing IAM Policy for Bedrock Access ==="
echo ""

# Get the Lambda execution role name
echo "1. Getting Lambda execution role..."
ROLE_NAME=$(aws iam list-roles --profile $AWS_PROFILE --query 'Roles[?contains(RoleName, `PublicCommentAnalyzerStac-LambdaExecutionRole`)].RoleName' --output text)
if [ -z "$ROLE_NAME" ]; then
    echo "❌ Could not find Lambda execution role"
    exit 1
fi
echo "✓ Found role: $ROLE_NAME"
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --profile $AWS_PROFILE --query 'Role.Arn' --output text)
echo "  ARN: $ROLE_ARN"
echo ""

# Get current policy document
echo "2. Getting current policy..."
POLICY_NAME="LambdaExecutionRoleDefaultPolicy6D69732F"
CURRENT_POLICY=$(aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" --profile $AWS_PROFILE --output json | jq '.PolicyDocument')
echo "✓ Retrieved current policy"
echo ""

# Check Bedrock permissions
echo "3. Current Bedrock permissions:"
echo "$CURRENT_POLICY" | jq '.Statement[] | select(.Action | type == "array" and contains(["bedrock:InvokeModel"]))'
echo ""

# Check Marketplace permissions
echo "4. Current Marketplace permissions:"
echo "$CURRENT_POLICY" | jq '.Statement[] | select(.Action | type == "array" and contains(["aws-marketplace:ViewSubscriptions"]))'
echo ""

# The policy should already be correct from CDK, but let's verify the resource ARN format
echo "5. Verifying resource ARN format..."
BEDROCK_RESOURCE=$(echo "$CURRENT_POLICY" | jq -r '.Statement[] | select(.Action | type == "array" and contains(["bedrock:InvokeModel"])) | .Resource')
echo "  Current Bedrock resource: $BEDROCK_RESOURCE"

if [[ "$BEDROCK_RESOURCE" == *"us.anthropic.*"* ]]; then
    echo "✓ Resource ARN includes us.anthropic.* pattern"
else
    echo "❌ Resource ARN does NOT include us.anthropic.* pattern"
    echo "  This needs to be fixed in the CDK stack"
fi
echo ""

echo "6. Testing if we need to add cross-region access..."
echo "  Note: us.anthropic models might be in a different region"
echo "  Current policy region: us-east-1"
echo ""

echo "=== Analysis Complete ==="
echo ""
echo "If the policy looks correct but Lambda still can't access Bedrock:"
echo "1. The Lambda function may be caching old credentials"
echo "2. Try deploying again to force Lambda to pick up new IAM permissions"
echo "3. Or wait 5-10 minutes for IAM changes to propagate"
