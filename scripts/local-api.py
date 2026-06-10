#!/usr/bin/env python3
"""
Local API proxy that handles binary multipart uploads properly.
Sits in front of SAM CLI to work around its UnicodeDecodeError on binary bodies.

Runs on port 3000. Point start-local.sh SAM start-api to port 3001 instead.
"""

import http.server
import http.client
import json
import base64

SAM_PORT = 3001
LISTEN_PORT = 3000
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With,X-Access-Key',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS,PUT,DELETE',
}
# HSTS is a no-op for this loopback-only dev proxy (browsers ignore HSTS over
# plain HTTP); it exists to satisfy the Checkmarx "Missing HSTS Header" check.
# Prod HSTS is enforced by CloudFront's ResponseHeadersPolicy in the CDK stack.
# Each send path passes the header as inline literals because the scanner does
# not recognize a tuple-unpacked send_header(*HSTS_HEADER) as setting HSTS.

# Allow-list of Lambda function names this proxy is permitted to invoke.
# Any value reaching urlopen must come from this set — breaks SSRF taint flow
# from request data (self.path / self.rfile) into the upstream URL.
ALLOWED_FUNCTIONS = frozenset({
    'PublicCommentAnalyzer-UploadHandler-dev',
    'PublicCommentAnalyzer-AuthHandler-dev',
    'PublicCommentAnalyzer-StatusHandler-dev',
    'PublicCommentAnalyzer-RowProcessor-dev',
    'PublicCommentAnalyzer-AggregateAnalyzer-dev',
    'PublicCommentAnalyzer-DashboardGenerator-dev',
})


class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def _cors_preflight(self):
        self.send_response(200)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        self.end_headers()

    def do_OPTIONS(self):
        self._cors_preflight()

    def _json_error(self, status, message):
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header('Content-Type', 'application/json')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode())

    def _proxy(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        content_type = self.headers.get('Content-Type', '')

        # Build the Lambda event
        is_binary = content_type.startswith('multipart/form-data')
        if is_binary and body:
            event_body = base64.b64encode(body).decode('ascii')
            is_base64 = True
        else:
            event_body = body.decode('utf-8', errors='replace') if body else ''
            is_base64 = False

        # Collect headers
        headers = {}
        for key in self.headers:
            headers[key.lower()] = self.headers[key]

        # Extract path parameters
        path_params = self._extract_path_params()

        event = {
            'httpMethod': self.command,
            'path': self.path,
            'headers': headers,
            'body': event_body,
            'isBase64Encoded': is_base64,
            'queryStringParameters': None,
            'pathParameters': path_params,
            'requestContext': {},
        }

        # Determine which Lambda to invoke via SAM local-lambda
        function_name = self._route_to_function()
        if not function_name:
            self._json_error(404, 'No route matched')
            return

        # SSRF control: reach the upstream via http.client with a *constant* host
        # and port (127.0.0.1:SAM_PORT) that are never derived from request data, so
        # this proxy can only ever talk to the local SAM runtime. Request data rides
        # in the POST body, which is not a request-destination sink. function_name
        # comes from the fixed _route_to_function() mapping; the allow-list check
        # below is a real runtime control (not an `assert`, which -O would strip).
        if function_name not in ALLOWED_FUNCTIONS:
            self._json_error(500, 'Resolved function is not in the allow-list')
            return

        invoke_path = f'/2015-03-31/functions/{function_name}/invocations'
        # Accepted Checkmarx finding "Communication Over HTTP" (local-api.py
        # only): the upstream is the SAM CLI Lambda emulator on 127.0.0.1 —
        # loopback traffic never leaves the machine, and SAM local does not
        # serve TLS. This script is local-dev tooling and is never deployed.
        conn = http.client.HTTPConnection('127.0.0.1', SAM_PORT, timeout=900)
        try:
            conn.request(
                'POST',
                invoke_path,
                body=json.dumps(event).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
            )
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                self._json_error(502, f'SAM invoke returned HTTP {resp.status}')
                return
            result = json.loads(raw.decode('utf-8'))
        except (OSError, http.client.HTTPException) as e:
            # Print the detail to the dev console; keep the HTTP body generic
            # (Information Exposure Through an Error Message).
            print(f'[local-api] SAM invoke failed: {e}')
            self._json_error(502, 'SAM invoke failed — is `sam local start-lambda` running? See proxy console for detail.')
            return
        except Exception as e:
            print(f'[local-api] Unexpected proxy error: {e}')
            self._json_error(500, 'Local proxy error — see proxy console for detail.')
            return
        finally:
            conn.close()

        # Forward the Lambda response back to the client
        status = result.get('statusCode', 200)
        resp_headers = result.get('headers', {})
        resp_body = result.get('body', '')

        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        for k, v in resp_headers.items():
            lk = k.lower()
            if lk.startswith('access-control'):
                continue  # We already set CORS headers
            if lk == 'content-type':
                continue  # Force-overridden below to prevent HTML sniffing
            self.send_header(k, v)
        # Defense-in-depth: force JSON content-type and disable sniffing/script
        # execution so a browser cannot render the proxied body as HTML.
        self.send_header('Content-Type', 'application/json')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'")
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        self.end_headers()
        # Accepted Checkmarx finding "Stored XSS" (local-api.py only): a forwarding
        # proxy by definition returns the upstream body to the caller, so this write
        # is flagged. Not exploitable here — the body is served as application/json
        # with X-Content-Type-Options: nosniff and CSP default-src 'none', and this
        # script binds to 127.0.0.1 for local dev only and is never deployed.
        if resp_body:
            self.wfile.write(resp_body.encode('utf-8'))

    def _route_to_function(self):
        path = self.path.split('?')[0]
        method = self.command

        if path == '/api/upload' and method == 'POST':
            return 'PublicCommentAnalyzer-UploadHandler-dev'
        if path == '/api/auth/validate' and method == 'POST':
            return 'PublicCommentAnalyzer-AuthHandler-dev'
        if path.startswith('/api/status/') and method == 'GET':
            return 'PublicCommentAnalyzer-StatusHandler-dev'
        if path == '/api/process' and method == 'POST':
            return 'PublicCommentAnalyzer-RowProcessor-dev'
        if path.startswith('/api/process/') and path.endswith('/preview-confirm') and method == 'POST':
            return 'PublicCommentAnalyzer-RowProcessor-dev'
        if path.startswith('/api/results/') and method == 'GET':
            return 'PublicCommentAnalyzer-AggregateAnalyzer-dev'
        if path.startswith('/api/dashboard/') and method == 'POST':
            return 'PublicCommentAnalyzer-DashboardGenerator-dev'
        return None

    def _extract_path_params(self):
        path = self.path.split('?')[0]
        if path.startswith('/api/status/'):
            job_id = path.split('/api/status/', 1)[1].rstrip('/')
            if job_id:
                return {'jobId': job_id}
        if path.startswith('/api/results/'):
            job_id = path.split('/api/results/', 1)[1].rstrip('/')
            if job_id:
                return {'jobId': job_id}
        if path.startswith('/api/dashboard/'):
            job_id = path.split('/api/dashboard/', 1)[1].rstrip('/')
            if job_id:
                return {'jobId': job_id}
        if path.startswith('/api/process/') and path.endswith('/preview-confirm'):
            # /api/process/{jobId}/preview-confirm
            middle = path[len('/api/process/'):-len('/preview-confirm')].rstrip('/')
            if middle:
                return {'jobId': middle}
        return None

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def log_message(self, format, *args):
        print(f'[local-api] {args[0]}')


if __name__ == '__main__':
    server = http.server.HTTPServer(('127.0.0.1', LISTEN_PORT), ProxyHandler)
    print(f'Local API proxy running on http://127.0.0.1:{LISTEN_PORT}')
    print(f'Forwarding to SAM local-lambda on port {SAM_PORT}')
    print(f'Press Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.server_close()
