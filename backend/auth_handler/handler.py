"""Validate the shared access password through the portable secret boundary."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from auth import _get_password_hash, _verify_password


def lambda_handler(event, context):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", ""),
        "Access-Control-Allow-Headers": "Content-Type,X-Access-Key",
    }
    try:
        body = json.loads(event.get("body", "{}") or "{}")
        if not isinstance(body, dict):
            raise ValueError("Expected an object")
        password = body.get("password", "")
    except (ValueError, TypeError):
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"valid": False, "message": "Invalid request"})}
    stored_hash = _get_password_hash()
    if not stored_hash:
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"valid": False, "message": "Auth not configured"})}
    valid = _verify_password(password, stored_hash)
    return {"statusCode": 200 if valid else 401, "headers": headers,
            "body": json.dumps({"valid": valid})}
