#!/bin/bash
# Start local development environment
# Uses a lightweight Python proxy on port 3000 that forwards to SAM local-lambda
# on port 3001. This works around SAM CLI's inability to handle binary uploads.
#
# Prerequisites: brew install aws-sam-cli, Docker running

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$PROJECT_ROOT/infrastructure/cdk.out/PublicCommentAnalyzerStack-dev.template.json"
ENV_VARS="$PROJECT_ROOT/local-env.json"
PROFILE="${AWS_PROFILE:-ncdit}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Public Comment Analyzer — Local Dev ===${NC}"

# Check prerequisites
if ! command -v sam &> /dev/null; then
    echo "SAM CLI not found. Install with: brew install aws-sam-cli"
    exit 1
fi

if ! docker info &> /dev/null 2>&1; then
    echo "Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Synth CDK template if needed
if [ ! -f "$TEMPLATE" ]; then
    echo -e "${YELLOW}Synthesizing CDK template...${NC}"
    cd "$PROJECT_ROOT/infrastructure"
    source "$PROJECT_ROOT/.venv/bin/activate" 2>/dev/null || true
    cdk synth --profile "$PROFILE" > /dev/null 2>&1
    echo -e "${GREEN}CDK template generated.${NC}"
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down local services..."
    kill $PROXY_PID $LAMBDA_PID 2>/dev/null
    wait $PROXY_PID $LAMBDA_PID 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# Start SAM local Lambda endpoint on port 3001
echo -e "${YELLOW}Starting SAM local Lambda on port 3001...${NC}"
sam local start-lambda \
    -t "$TEMPLATE" \
    --env-vars "$ENV_VARS" \
    --profile "$PROFILE" \
    --warm-containers EAGER \
    --port 3001 &
LAMBDA_PID=$!

# Give SAM a moment to start
sleep 3

# Start local API proxy on port 3000
echo -e "${YELLOW}Starting API proxy on port 3000...${NC}"
python3 -u "$SCRIPT_DIR/local-api.py" &
PROXY_PID=$!

echo ""
echo -e "${GREEN}=== Local services running ===${NC}"
echo -e "  API:     http://localhost:3000  (proxy → SAM)"
echo -e "  Lambda:  http://localhost:3001  (SAM runtime)"
echo -e ""
echo -e "  Start frontend in another terminal:"
echo -e "    cd frontend && npm start"
echo -e ""
echo -e "  Frontend: http://localhost:4200"
echo -e "  Password: (whatever the LOCAL_PASSWORD_HASH in local-env.json hashes back to)"
echo -e ""
echo -e "Press Ctrl+C to stop all services."

wait
