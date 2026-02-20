#!/bin/bash
set -e

# Load environment variables
if [ -f .env ]; then
  export $(cat .env | grep -v '^#' | xargs)
fi

# Use AWS_PROFILE from environment or default to 'default'
AWS_PROFILE=${AWS_PROFILE:-default}
API_URL="https://emu57xwa0c.execute-api.us-east-1.amazonaws.com/dev"
TEST_FILE="$HOME/Downloads/test-comments-100.csv"

if [ ! -f "$TEST_FILE" ]; then
    echo "❌ Test file not found: $TEST_FILE"
    exit 1
fi

echo "=== End-to-End Test ==="
echo ""

# Step 1: Upload file
echo "1. Uploading test file..."
UPLOAD_RESPONSE=$(curl -s -X POST "$API_URL/api/upload" \
    -F "file=@$TEST_FILE" \
    -H "Accept: application/json")

echo "Upload response: $UPLOAD_RESPONSE"

FILE_ID=$(echo "$UPLOAD_RESPONSE" | jq -r '.fileId')
if [ "$FILE_ID" == "null" ] || [ -z "$FILE_ID" ]; then
    echo "❌ Upload failed"
    exit 1
fi
echo "✓ File uploaded: $FILE_ID"
echo ""

# Step 2: Start processing
echo "2. Starting processing..."
PROCESS_RESPONSE=$(curl -s -X POST "$API_URL/api/process" \
    -H "Content-Type: application/json" \
    -d "{
        \"fileId\": \"$FILE_ID\",
        \"analysisColumns\": [
            {
                \"name\": \"Sentiment\",
                \"instructions\": \"Classify as 'pro' or 'against'\"
            },
            {
                \"name\": \"Rating\",
                \"instructions\": \"Rate from 1-7 where 1 is strongly against and 7 is strongly pro\"
            }
        ]
    }")

echo "Process response: $PROCESS_RESPONSE"

JOB_ID=$(echo "$PROCESS_RESPONSE" | jq -r '.jobId')
if [ "$JOB_ID" == "null" ] || [ -z "$JOB_ID" ]; then
    echo "❌ Processing start failed"
    exit 1
fi
echo "✓ Processing started: $JOB_ID"
echo ""

# Step 3: Monitor status
echo "3. Monitoring processing status..."
for i in {1..60}; do
    sleep 2
    STATUS_RESPONSE=$(curl -s "$API_URL/api/status/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
    PROGRESS=$(echo "$STATUS_RESPONSE" | jq -r '.progress')
    COMPLETED=$(echo "$STATUS_RESPONSE" | jq -r '.completedRows')
    TOTAL=$(echo "$STATUS_RESPONSE" | jq -r '.totalRows')
    
    echo "  Status: $STATUS | Progress: $PROGRESS% ($COMPLETED/$TOTAL)"
    
    if [ "$STATUS" == "completed" ]; then
        echo "✓ Processing completed!"
        break
    elif [ "$STATUS" == "failed" ]; then
        echo "❌ Processing failed"
        echo "$STATUS_RESPONSE" | jq '.errors'
        exit 1
    fi
done

# Step 4: Check logs
echo ""
echo "4. Checking Lambda logs..."
aws logs tail /aws/lambda/PublicCommentAnalyzer-RowProcessor-dev --since 5m --profile $AWS_PROFILE 2>&1 | grep -E "(ERROR|Bedrock|SUCCESS)" | tail -20

echo ""
echo "=== Test Complete ==="
echo "Job ID: $JOB_ID"
