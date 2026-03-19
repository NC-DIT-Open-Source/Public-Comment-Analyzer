#!/bin/bash
# Deployment script for Public Comment Analyzer with custom domain

set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# Use AWS_PROFILE from environment or default to 'default'
AWS_PROFILE=${AWS_PROFILE:-default}

# Configuration
DOMAIN_NAME="commentreviewer.oaip.nc.gov"
ENVIRONMENT="prod"

echo "🚀 Deploying Public Comment Analyzer to $DOMAIN_NAME"
echo ""

# Check if certificate ARN is provided
if [ -z "$CERTIFICATE_ARN" ]; then
  echo "❌ Error: CERTIFICATE_ARN environment variable is required"
  echo ""
  echo "Usage:"
  echo "  export CERTIFICATE_ARN=arn:aws:acm:us-east-1:ACCOUNT:certificate/CERT_ID"
  echo "  ./scripts/deploy-custom-domain.sh"
  echo ""
  echo "To get or create a certificate:"
  echo "  1. Request certificate in us-east-1:"
  echo "     aws acm request-certificate \\"
  echo "       --domain-name $DOMAIN_NAME \\"
  echo "       --validation-method DNS \\"
  echo "       --region us-east-1 \\"
  echo "       --profile \$AWS_PROFILE"
  echo ""
  echo "  2. List certificates:"
  echo "     aws acm list-certificates --region us-east-1 --profile \$AWS_PROFILE"
  exit 1
fi

echo "📋 Configuration:"
echo "   Domain: $DOMAIN_NAME"
echo "   Environment: $ENVIRONMENT"
echo "   Certificate: $CERTIFICATE_ARN"
echo ""

# Deploy infrastructure
echo "🏗️  Deploying infrastructure..."
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

CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE | sed 's|https://||')

CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name PublicCommentAnalyzerStack-$ENVIRONMENT \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text \
  --profile $AWS_PROFILE)

echo "   Frontend bucket: $FRONTEND_BUCKET"
echo "   CloudFront domain: $CLOUDFRONT_DOMAIN"
echo "   Distribution ID: $CLOUDFRONT_DIST_ID"

# Build and deploy frontend
if [ -d "../frontend" ]; then
  echo ""
  echo "🎨 Building and deploying frontend..."
  cd ../frontend
  npm install
  npm run build:prod
  
  aws s3 sync dist/public-comment-app/browser/ s3://$FRONTEND_BUCKET/ --delete --profile $AWS_PROFILE
  
  echo ""
  echo "🔄 Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --distribution-id $CLOUDFRONT_DIST_ID \
    --paths "/*" \
    --profile $AWS_PROFILE
  
  echo "✅ Frontend deployed"
else
  echo "⚠️  Frontend directory not found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Deployment complete!"
echo ""
echo "📝 Next steps:"
echo ""
echo "1. Create DNS record pointing to CloudFront:"
echo "   Domain: $DOMAIN_NAME"
echo "   Target: $CLOUDFRONT_DOMAIN"
echo ""
echo "   For Route 53 ALIAS record:"
echo "   aws route53 change-resource-record-sets \\"
echo "     --hosted-zone-id <YOUR_HOSTED_ZONE_ID> \\"
echo "     --change-batch '{"
echo "       \"Changes\": [{"
echo "         \"Action\": \"CREATE\","
echo "         \"ResourceRecordSet\": {"
echo "           \"Name\": \"$DOMAIN_NAME\","
echo "           \"Type\": \"A\","
echo "           \"AliasTarget\": {"
echo "             \"HostedZoneId\": \"Z2FDTNDATAQYW2\","
echo "             \"DNSName\": \"$CLOUDFRONT_DOMAIN\","
echo "             \"EvaluateTargetHealth\": false"
echo "           }"
echo "         }"
echo "       }]"
echo "     }' \\"
echo "     --profile \$AWS_PROFILE"
echo ""
echo "2. Wait for DNS propagation (can take 5-60 minutes)"
echo ""
echo "3. Test your deployment:"
echo "   curl -I https://$DOMAIN_NAME"
echo ""
echo "🔒 Security features enabled:"
echo "   ✓ CORS restricted to https://$DOMAIN_NAME"
echo "   ✓ HTTPS enforced with HSTS"
echo "   ✓ Security headers (X-Frame-Options, CSP, etc.)"
echo "   ✓ File upload validation (size, type, content)"
echo "   ✓ Input sanitization and prompt injection protection"
echo "   ✓ Rate limiting on API Gateway"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
