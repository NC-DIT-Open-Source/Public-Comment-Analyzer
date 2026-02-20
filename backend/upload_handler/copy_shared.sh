#!/bin/bash
# Copy shared module files to upload_handler for Lambda deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/../shared"

# Copy shared Python files (excluding tests)
cp "$SHARED_DIR/file_parser.py" "$SCRIPT_DIR/"
cp "$SHARED_DIR/__init__.py" "$SCRIPT_DIR/"

echo "Shared files copied to upload_handler directory"
