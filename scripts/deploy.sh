#!/bin/bash
# Deployment script for Public Comment Analyzer

set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# Use AWS_PROFILE from environment or default to 'default'
AWS_PROFILE=${AWS_PROFILE:-default}
ENVIRONMENT=${1:-dev}

echo "Deploying Public Comment Analyzer to $ENVIRONMENT environment..."
echo "Using AWS profile: $AWS_PROFILE"

# Deploy infrastructure
echo "Deploying infrastructure..."
cd infrastructure
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate
pip install -q -r requirements.txt
cdk deploy --context environment=$ENVIRONMENT --require-approval never --profile $AWS_PROFILE

# Get outputs
FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE)

CLOUDFRONT_DIST=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE | sed 's/https:\/\///' | sed 's/\/.*//')

echo "Frontend bucket: $FRONTEND_BUCKET"
echo "CloudFront distribution: $CLOUDFRONT_DIST"

# Build and deploy frontend (if exists)
if [ -d "../frontend" ]; then
  echo "Building and deploying frontend..."
  cd ../frontend
  npm install
  npm run build
  
  aws s3 sync dist/public-comment-app/ s3://$FRONTEND_BUCKET/ --delete --profile $AWS_PROFILE
  
  # Invalidate CloudFront cache
  aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DIST --paths "/*" --profile $AWS_PROFILE
  
  echo "Frontend deployed successfully!"
else
  echo "Frontend not yet created. Run task 9 to create Angular application."
fi

echo "Deployment complete!"
echo "CloudFront URL: https://$CLOUDFRONT_DIST"
