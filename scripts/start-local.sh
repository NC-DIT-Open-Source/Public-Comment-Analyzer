#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v npm >/dev/null || { echo "Install Node.js 24.15 or newer in the 24.x series."; exit 1; }
node -e 'const [a,b,c]=process.versions.node.split(".").map(Number); if (!((a===24&&b>=15)||(a===22&&(b>22||(b===22&&c>=3)))||a===26)) { console.error("Use supported Node 24.15+ (24.x), 22.22.3+ (22.x), or 26.x."); process.exit(1); }'
uv sync --frozen --extra providers
uv run --frozen python scripts/setup-local.py
(cd frontend && HUSKY=0 npm ci && npm run build:prod)
exec uv run --frozen --env-file .env uvicorn backend.local.app:app --host 127.0.0.1 --port 8000 --no-access-log
