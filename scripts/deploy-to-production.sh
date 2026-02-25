#!/bin/bash
# Deploy to commentreviewer.oaip.nc.gov

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DOMAIN_NAME="commentreviewer.oaip.nc.gov"
CERTIFICATE_ARN="arn:aws:acm:us-east-1:267527030320:certificate/7716fd46-be8f-42cf-834c-783b9d7e58d9"
ENVIRONMENT="prod"

echo "🔍 Checking certificate validation status..."
CERT_STATUS=$(aws acm describe-certificate \
  --certificate-arn $CERTIFICATE_ARN \
  --region us-east-1 \
  --profile $AWS_PROFILE \
  --query 'Certificate.Status' \
  --output text)

echo "   Certificate status: $CERT_STATUS"

if [ "$CERT_STATUS" != "ISSUED" ]; then
    echo ""
    echo "❌ Certificate is not yet validated (status: $CERT_STATUS)"
    echo ""
    echo "Please add this DNS validation record:"
    aws acm describe-certificate \
      --certificate-arn $CERTIFICATE_ARN \
      --region us-east-1 \
      --profile $AWS_PROFILE \
      --query 'Certificate.DomainValidationOptions[0].ResourceRecord' \
      --output table
    echo ""
    echo "After adding the record, wait a few minutes and run this script again."
    exit 1
fi

echo "✅ Certificate is validated!"
echo ""
echo "🚀 Deploying to $DOMAIN_NAME..."
echo ""

# Deploy infrastructure
echo "📦 Deploying infrastructure..."
cd infrastructure
source ../.venv/bin/activate 2>/dev/null || (cd .. && python3 -m venv .venv && source .venv/bin/activate && cd infrastructure)
pip install -q -r requirements.txt

cdk deploy \
  --context environment=$ENVIRONMENT \
  --context domain_name=$DOMAIN_NAME \
  --context certificate_arn=$CERTIFICATE_ARN \
  --context allowed_origin=https://$DOMAIN_NAME \
  --require-approval never \
  --profile $AWS_PROFILE

echo ""
echo "✅ Infrastructure deployed"

# Get outputs
echo ""
echo "📊 Getting deployment outputs..."
FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE)

CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE)

echo "   Frontend bucket: $FRONTEND_BUCKET"
echo "   Distribution ID: $CLOUDFRONT_DIST_ID"

# Build and deploy frontend
echo ""
echo "🎨 Building and deploying frontend..."
cd ../frontend/public-comment-app
npm install
npm run build:prod

aws s3 sync dist/public-comment-app/browser/ s3://$FRONTEND_BUCKET/ --delete --profile $AWS_PROFILE

echo ""
echo "🔄 Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id $CLOUDFRONT_DIST_ID \
  --paths "/*" \
  --profile $AWS_PROFILE \
  --output json | grep -E '(Id|Status)'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Deployment complete!"
echo ""
echo "🌐 Your application is now live at:"
echo "   https://$DOMAIN_NAME"
echo ""
echo "🔒 Security features enabled:"
echo "   ✓ CORS restricted to https://$DOMAIN_NAME"
echo "   ✓ HTTPS enforced with HSTS preload"
echo "   ✓ Security headers (X-Frame-Options, CSP, etc.)"
echo "   ✓ File upload validation (100MB max, 50k rows max)"
echo "   ✓ Input sanitization and prompt injection protection"
echo "   ✓ Rate limiting (100 req/s, 200 burst)"
echo ""
echo "🧪 Test your deployment:"
echo "   curl -I https://$DOMAIN_NAME"
echo ""
echo "Note: CloudFront distribution may take 10-15 minutes to fully deploy."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
