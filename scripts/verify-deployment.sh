#!/bin/bash
# Deployment verification script for Public Comment Analyzer

set -e

ENVIRONMENT=${1:-dev}
STACK_NAME="PublicCommentAnalyzerStack-${ENVIRONMENT}"

echo "🔍 Verifying Public Comment Analyzer deployment"
echo "   Environment: $ENVIRONMENT"
echo "   Stack: $STACK_NAME"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
ALL_CHECKS_PASSED=true

# Helper functions
check_passed() {
  echo -e "${GREEN}✅ $1${NC}"
}

check_failed() {
  echo -e "${RED}❌ $1${NC}"
  ALL_CHECKS_PASSED=false
}

check_warning() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
  check_failed "AWS CLI is not installed"
  exit 1
fi

# Check if stack exists
echo "📋 Checking CloudFormation stack..."
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
  STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].StackStatus" \
    --output text)
  
  if [ "$STACK_STATUS" == "CREATE_COMPLETE" ] || [ "$STACK_STATUS" == "UPDATE_COMPLETE" ]; then
    check_passed "Stack exists and is in good state: $STACK_STATUS"
  else
    check_failed "Stack exists but is in unexpected state: $STACK_STATUS"
  fi
else
  check_failed "Stack does not exist. Please deploy infrastructure first."
  exit 1
fi

# Get stack outputs
echo ""
echo "📋 Reading stack outputs..."
DATA_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" \
  --output text)

FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text)

JOBS_TABLE=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='JobsTableName'].OutputValue" \
  --output text)

API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text)

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text)

CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text)

echo "   Data Bucket: $DATA_BUCKET"
echo "   Frontend Bucket: $FRONTEND_BUCKET"
echo "   Jobs Table: $JOBS_TABLE"
echo "   API URL: $API_URL"
echo "   CloudFront URL: $CLOUDFRONT_URL"
echo "   CloudFront Distribution ID: $CLOUDFRONT_DIST_ID"

# Check S3 buckets
echo ""
echo "📦 Checking S3 buckets..."

if aws s3 ls "s3://$DATA_BUCKET" &> /dev/null; then
  check_passed "Data bucket exists: $DATA_BUCKET"
  
  # Check encryption
  ENCRYPTION=$(aws s3api get-bucket-encryption --bucket "$DATA_BUCKET" 2>&1)
  if echo "$ENCRYPTION" | grep -q "AES256\|aws:kms"; then
    check_passed "Data bucket has encryption enabled"
  else
    check_warning "Data bucket encryption not detected"
  fi
  
  # Check lifecycle policy
  if aws s3api get-bucket-lifecycle-configuration --bucket "$DATA_BUCKET" &> /dev/null; then
    check_passed "Data bucket has lifecycle policy configured"
  else
    check_warning "Data bucket lifecycle policy not found"
  fi
  
  # Check CORS
  if aws s3api get-bucket-cors --bucket "$DATA_BUCKET" &> /dev/null; then
    check_passed "Data bucket has CORS configured"
  else
    check_warning "Data bucket CORS not configured"
  fi
else
  check_failed "Data bucket does not exist: $DATA_BUCKET"
fi

if aws s3 ls "s3://$FRONTEND_BUCKET" &> /dev/null; then
  check_passed "Frontend bucket exists: $FRONTEND_BUCKET"
  
  # Check if frontend is deployed
  if aws s3 ls "s3://$FRONTEND_BUCKET/index.html" &> /dev/null; then
    check_passed "Frontend files are deployed (index.html found)"
  else
    check_warning "Frontend files not deployed yet (index.html not found)"
  fi
else
  check_failed "Frontend bucket does not exist: $FRONTEND_BUCKET"
fi

# Check DynamoDB table
echo ""
echo "🗄️  Checking DynamoDB table..."

if aws dynamodb describe-table --table-name "$JOBS_TABLE" &> /dev/null; then
  check_passed "DynamoDB table exists: $JOBS_TABLE"
  
  TABLE_STATUS=$(aws dynamodb describe-table \
    --table-name "$JOBS_TABLE" \
    --query "Table.TableStatus" \
    --output text)
  
  if [ "$TABLE_STATUS" == "ACTIVE" ]; then
    check_passed "DynamoDB table is active"
  else
    check_warning "DynamoDB table status: $TABLE_STATUS"
  fi
  
  # Check encryption
  ENCRYPTION=$(aws dynamodb describe-table \
    --table-name "$JOBS_TABLE" \
    --query "Table.SSEDescription.Status" \
    --output text)
  
  if [ "$ENCRYPTION" == "ENABLED" ]; then
    check_passed "DynamoDB table has encryption enabled"
  else
    check_warning "DynamoDB table encryption not detected"
  fi
  
  # Check point-in-time recovery
  PITR=$(aws dynamodb describe-continuous-backups \
    --table-name "$JOBS_TABLE" \
    --query "ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus" \
    --output text)
  
  if [ "$PITR" == "ENABLED" ]; then
    check_passed "DynamoDB table has point-in-time recovery enabled"
  else
    check_warning "DynamoDB table point-in-time recovery not enabled"
  fi
else
  check_failed "DynamoDB table does not exist: $JOBS_TABLE"
fi

# Check Lambda functions
echo ""
echo "⚡ Checking Lambda functions..."

LAMBDA_FUNCTIONS=(
  "PublicCommentAnalyzer-UploadHandler-${ENVIRONMENT}"
  "PublicCommentAnalyzer-RowProcessor-${ENVIRONMENT}"
  "PublicCommentAnalyzer-AggregateAnalyzer-${ENVIRONMENT}"
  "PublicCommentAnalyzer-StatusHandler-${ENVIRONMENT}"
)

for FUNCTION_NAME in "${LAMBDA_FUNCTIONS[@]}"; do
  if aws lambda get-function --function-name "$FUNCTION_NAME" &> /dev/null; then
    check_passed "Lambda function exists: $FUNCTION_NAME"
    
    # Check runtime
    RUNTIME=$(aws lambda get-function-configuration \
      --function-name "$FUNCTION_NAME" \
      --query "Runtime" \
      --output text)
    
    if [[ "$RUNTIME" == python3.* ]]; then
      check_passed "  Runtime: $RUNTIME"
    else
      check_warning "  Unexpected runtime: $RUNTIME"
    fi
    
    # Check environment variables
    ENV_VARS=$(aws lambda get-function-configuration \
      --function-name "$FUNCTION_NAME" \
      --query "Environment.Variables" \
      --output json)
    
    if echo "$ENV_VARS" | grep -q "DATA_BUCKET\|JOBS_TABLE"; then
      check_passed "  Environment variables configured"
    else
      check_warning "  Environment variables may not be configured"
    fi
  else
    check_failed "Lambda function does not exist: $FUNCTION_NAME"
  fi
done

# Check API Gateway
echo ""
echo "🌐 Checking API Gateway..."

if [ -n "$API_URL" ]; then
  check_passed "API Gateway URL exists: $API_URL"
  
  # Test API endpoint (should return 400 or 404, not 403)
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}api/status/test" || echo "000")
  
  if [ "$HTTP_CODE" == "404" ] || [ "$HTTP_CODE" == "400" ]; then
    check_passed "API Gateway is accessible (HTTP $HTTP_CODE)"
  elif [ "$HTTP_CODE" == "403" ]; then
    check_warning "API Gateway returned 403 - check permissions"
  elif [ "$HTTP_CODE" == "000" ]; then
    check_warning "Could not reach API Gateway - check network/DNS"
  else
    check_warning "API Gateway returned unexpected status: $HTTP_CODE"
  fi
else
  check_failed "API Gateway URL not found in stack outputs"
fi

# Check CloudFront distribution
echo ""
echo "☁️  Checking CloudFront distribution..."

if [ -n "$CLOUDFRONT_DIST_ID" ]; then
  check_passed "CloudFront distribution ID exists: $CLOUDFRONT_DIST_ID"
  
  DIST_STATUS=$(aws cloudfront get-distribution \
    --id "$CLOUDFRONT_DIST_ID" \
    --query "Distribution.Status" \
    --output text)
  
  if [ "$DIST_STATUS" == "Deployed" ]; then
    check_passed "CloudFront distribution is deployed"
  else
    check_warning "CloudFront distribution status: $DIST_STATUS (may still be deploying)"
  fi
  
  # Check if CloudFront URL is accessible
  if [ -n "$CLOUDFRONT_URL" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$CLOUDFRONT_URL" || echo "000")
    
    if [ "$HTTP_CODE" == "200" ]; then
      check_passed "CloudFront URL is accessible: $CLOUDFRONT_URL"
    elif [ "$HTTP_CODE" == "403" ]; then
      check_warning "CloudFront returned 403 - frontend may not be deployed yet"
    elif [ "$HTTP_CODE" == "000" ]; then
      check_warning "Could not reach CloudFront - check network/DNS"
    else
      check_warning "CloudFront returned status: $HTTP_CODE"
    fi
  fi
else
  check_failed "CloudFront distribution ID not found in stack outputs"
fi

# Check resource tags
echo ""
echo "🏷️  Checking resource tags..."

# Check S3 bucket tags
if [ -n "$DATA_BUCKET" ]; then
  TAGS=$(aws s3api get-bucket-tagging --bucket "$DATA_BUCKET" 2>&1 || echo "")
  
  if echo "$TAGS" | grep -q "Application.*PublicCommentAnalyzer"; then
    check_passed "Data bucket has Application tag"
  else
    check_warning "Data bucket missing Application tag"
  fi
  
  if echo "$TAGS" | grep -q "Environment.*${ENVIRONMENT}"; then
    check_passed "Data bucket has Environment tag"
  else
    check_warning "Data bucket missing Environment tag"
  fi
  
  if echo "$TAGS" | grep -q "ManagedBy"; then
    check_passed "Data bucket has ManagedBy tag"
  else
    check_warning "Data bucket missing ManagedBy tag"
  fi
fi

# Check DynamoDB table tags
if [ -n "$JOBS_TABLE" ]; then
  TABLE_ARN=$(aws dynamodb describe-table \
    --table-name "$JOBS_TABLE" \
    --query "Table.TableArn" \
    --output text)
  
  TAGS=$(aws dynamodb list-tags-of-resource --resource-arn "$TABLE_ARN" 2>&1 || echo "")
  
  if echo "$TAGS" | grep -q "Application.*PublicCommentAnalyzer"; then
    check_passed "DynamoDB table has Application tag"
  else
    check_warning "DynamoDB table missing Application tag"
  fi
fi

# Summary
echo ""
echo "=" | awk '{for(i=0;i<60;i++)printf "="; printf "\n"}'

if [ "$ALL_CHECKS_PASSED" = true ]; then
  echo -e "${GREEN}✅ All checks passed! Deployment is healthy.${NC}"
  echo ""
  echo "Next steps:"
  echo "  1. Deploy frontend: cd frontend && npm run deploy"
  echo "  2. Access application: $CLOUDFRONT_URL"
  echo "  3. Test complete workflow with sample data"
  exit 0
else
  echo -e "${YELLOW}⚠️  Some checks failed or returned warnings.${NC}"
  echo ""
  echo "Review the output above and fix any issues."
  echo "Check CloudWatch Logs for detailed error messages."
  exit 1
fi
