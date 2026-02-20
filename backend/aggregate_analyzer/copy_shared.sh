#!/bin/bash
# Copy shared modules to aggregate_analyzer directory for Lambda deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/../shared"

# Copy shared modules
cp "$SHARED_DIR/file_parser.py" "$SCRIPT_DIR/"

echo "Shared modules copied to aggregate_analyzer directory"
