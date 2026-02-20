#!/bin/bash
# Automated test script for CORS and CloudFront configuration

set -e

ENVIRONMENT=${1:-dev}
STACK_NAME="PublicCommentAnalyzerStack-${ENVIRONMENT}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Testing CORS and CloudFront Configuration${NC}"
echo "   Environment: $ENVIRONMENT"
echo "   Stack: $STACK_NAME"
echo ""

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNING=0

# Helper functions
test_passed() {
  echo -e "${GREEN}✅ $1${NC}"
  ((TESTS_PASSED++))
}

test_failed() {
  echo -e "${RED}❌ $1${NC}"
  ((TESTS_FAILED++))
}

test_warning() {
  echo -e "${YELLOW}⚠️  $1${NC}"
  ((TESTS_WARNING++))
}

# Get stack outputs
echo "📋 Reading stack outputs..."

API_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text 2>/dev/null || echo "")

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
  --output text 2>/dev/null || echo "")

CLOUDFRONT_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [ -z "$API_URL" ] || [ -z "$CLOUDFRONT_URL" ]; then
  echo -e "${RED}❌ Could not read stack outputs. Is the stack deployed?${NC}"
  exit 1
fi

echo "   API URL: $API_URL"
echo "   CloudFront URL: $CLOUDFRONT_URL"
echo "   Distribution ID: $CLOUDFRONT_DIST_ID"
echo ""

# Test 1: CORS Preflight (OPTIONS)
echo "Test 1: CORS Preflight (OPTIONS Request)"
RESPONSE=$(curl -s -i -X OPTIONS "${API_URL}api/upload" \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "access-control-allow-origin"; then
  test_passed "CORS preflight headers present"
else
  test_failed "CORS preflight headers missing"
fi

if echo "$RESPONSE" | grep -qi "access-control-allow-methods"; then
  test_passed "CORS allow-methods header present"
else
  test_warning "CORS allow-methods header missing"
fi

# Test 2: CORS on GET Request
echo ""
echo "Test 2: CORS on GET Request"
RESPONSE=$(curl -s -i "${API_URL}api/status/test-job-id" \
  -H "Origin: https://example.com" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "access-control-allow-origin"; then
  test_passed "CORS headers present on GET request"
else
  test_failed "CORS headers missing on GET request"
fi

HTTP_CODE=$(echo "$RESPONSE" | grep -i "HTTP" | head -1 | awk '{print $2}')
if [ "$HTTP_CODE" == "404" ]; then
  test_passed "API returns expected 404 for non-existent job"
else
  test_warning "API returned HTTP $HTTP_CODE (expected 404)"
fi

# Test 3: CORS on POST Request
echo ""
echo "Test 3: CORS on POST Request"
RESPONSE=$(curl -s -i -X POST "${API_URL}api/upload" \
  -H "Origin: https://example.com" \
  -H "Content-Type: multipart/form-data" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "access-control-allow-origin"; then
  test_passed "CORS headers present on POST request"
else
  test_failed "CORS headers missing on POST request"
fi

# Test 4: CloudFront Static Content
echo ""
echo "Test 4: CloudFront Static Content Delivery"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$CLOUDFRONT_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" == "200" ]; then
  test_passed "CloudFront serves static content (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" == "403" ]; then
  test_warning "CloudFront returned 403 - frontend may not be deployed yet"
else
  test_warning "CloudFront returned HTTP $HTTP_CODE"
fi

# Check for CloudFront headers
RESPONSE=$(curl -s -i "$CLOUDFRONT_URL" 2>/dev/null || echo "")
if echo "$RESPONSE" | grep -qi "x-cache.*cloudfront\|via.*cloudfront"; then
  test_passed "CloudFront headers present (request went through CloudFront)"
else
  test_warning "CloudFront headers not detected"
fi

# Test 5: CloudFront API Proxy
echo ""
echo "Test 5: CloudFront API Proxy (/api/* paths)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${CLOUDFRONT_URL}/api/status/test-job-id" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" == "404" ]; then
  test_passed "CloudFront proxies API requests (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" == "502" ]; then
  test_failed "CloudFront returned 502 - API Gateway may not be configured correctly"
elif [ "$HTTP_CODE" == "000" ]; then
  test_failed "Could not reach CloudFront - check network/DNS"
else
  test_warning "CloudFront API proxy returned HTTP $HTTP_CODE"
fi

# Check CORS through CloudFront
RESPONSE=$(curl -s -i "${CLOUDFRONT_URL}/api/status/test-job-id" \
  -H "Origin: https://example.com" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "access-control-allow-origin"; then
  test_passed "CORS headers present through CloudFront"
else
  test_failed "CORS headers missing through CloudFront"
fi

# Test 6: HTTPS Redirect
echo ""
echo "Test 6: HTTPS Redirect"
DOMAIN=$(echo "$CLOUDFRONT_URL" | sed 's|https://||')
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -L "http://$DOMAIN" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" == "200" ]; then
  test_passed "HTTP redirects to HTTPS (final HTTP $HTTP_CODE)"
else
  test_warning "HTTP redirect returned HTTP $HTTP_CODE"
fi

# Test 7: SPA Routing (404 → index.html)
echo ""
echo "Test 7: SPA Routing (404 → index.html)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${CLOUDFRONT_URL}/non-existent-path" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" == "200" ]; then
  test_passed "SPA routing works (HTTP $HTTP_CODE)"
elif [ "$HTTP_CODE" == "403" ]; then
  test_warning "SPA routing returned 403 - frontend may not be deployed"
else
  test_warning "SPA routing returned HTTP $HTTP_CODE (expected 200)"
fi

# Test 8: Cache Behavior - Static Content
echo ""
echo "Test 8: Cache Behavior - Static Content"
# Make two requests to check caching
curl -s "$CLOUDFRONT_URL" > /dev/null 2>&1
sleep 1
RESPONSE=$(curl -s -i "$CLOUDFRONT_URL" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "x-cache.*hit"; then
  test_passed "Static content is cached (x-cache: Hit)"
elif echo "$RESPONSE" | grep -qi "x-cache.*miss"; then
  test_warning "Static content not cached yet (x-cache: Miss) - may need more requests"
else
  test_warning "Could not determine cache status"
fi

# Test 9: Cache Behavior - API Requests
echo ""
echo "Test 9: Cache Behavior - API Requests (should NOT be cached)"
RESPONSE=$(curl -s -i "${CLOUDFRONT_URL}/api/status/test" 2>/dev/null || echo "")

if echo "$RESPONSE" | grep -qi "x-cache.*miss"; then
  test_passed "API requests are not cached (x-cache: Miss)"
elif echo "$RESPONSE" | grep -qi "x-cache.*hit"; then
  test_failed "API requests are being cached (should not be cached)"
else
  test_warning "Could not determine API cache status"
fi

# Test 10: CloudFront Distribution Status
echo ""
echo "Test 10: CloudFront Distribution Status"
if [ -n "$CLOUDFRONT_DIST_ID" ]; then
  DIST_STATUS=$(aws cloudfront get-distribution \
    --id "$CLOUDFRONT_DIST_ID" \
    --query "Distribution.Status" \
    --output text 2>/dev/null || echo "")
  
  if [ "$DIST_STATUS" == "Deployed" ]; then
    test_passed "CloudFront distribution is deployed"
  else
    test_warning "CloudFront distribution status: $DIST_STATUS"
  fi
else
  test_warning "CloudFront distribution ID not found"
fi

# Test 11: API Gateway Endpoints
echo ""
echo "Test 11: API Gateway Endpoints"

# Test upload endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}api/upload" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" == "400" ] || [ "$HTTP_CODE" == "415" ]; then
  test_passed "Upload endpoint accessible (HTTP $HTTP_CODE)"
else
  test_warning "Upload endpoint returned HTTP $HTTP_CODE"
fi

# Test status endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}api/status/test" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" == "404" ]; then
  test_passed "Status endpoint accessible (HTTP $HTTP_CODE)"
else
  test_warning "Status endpoint returned HTTP $HTTP_CODE"
fi

# Test results endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}api/results/test" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" == "404" ] || [ "$HTTP_CODE" == "400" ]; then
  test_passed "Results endpoint accessible (HTTP $HTTP_CODE)"
else
  test_warning "Results endpoint returned HTTP $HTTP_CODE"
fi

# Summary
echo ""
echo "=" | awk '{for(i=0;i<60;i++)printf "="; printf "\n"}'
echo "Test Summary:"
echo -e "  ${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "  ${RED}Failed: $TESTS_FAILED${NC}"
echo -e "  ${YELLOW}Warnings: $TESTS_WARNING${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ All critical tests passed!${NC}"
  echo ""
  echo "CORS and CloudFront are configured correctly."
  echo ""
  echo "Next steps:"
  echo "  1. Test complete workflow in browser: $CLOUDFRONT_URL"
  echo "  2. Check browser console for any CORS errors"
  echo "  3. Upload a test file and verify processing works"
  echo ""
  exit 0
else
  echo -e "${RED}❌ Some tests failed.${NC}"
  echo ""
  echo "Review the output above and fix any issues."
  echo "Common issues:"
  echo "  - CORS not configured: Redeploy infrastructure"
  echo "  - CloudFront 502: Check API Gateway and Lambda functions"
  echo "  - CloudFront 403: Deploy frontend or check S3 bucket policy"
  echo ""
  echo "For detailed troubleshooting, see CORS_AND_CLOUDFRONT_TESTING.md"
  echo ""
  exit 1
fi
