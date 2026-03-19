#!/usr/bin/env python3
"""
Local API proxy that handles binary multipart uploads properly.
Sits in front of SAM CLI to work around its UnicodeDecodeError on binary bodies.

Runs on port 3000. Point start-local.sh SAM start-api to port 3001 instead.
"""

import http.server
import json
import base64
import urllib.request
import urllib.error

SAM_PORT = 3001
LISTEN_PORT = 3000
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Requested-With,X-Access-Key',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS,PUT,DELETE',
}


class ProxyHandler(http.server.BaseHTTPRequestHandler):

    def _cors_preflight(self):
        self.send_response(200)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_OPTIONS(self):
        self._cors_preflight()

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
            self.send_response(404)
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'No route matched'}).encode())
            return

        # Invoke via SAM local lambda endpoint
        try:
            invoke_url = f'http://127.0.0.1:{SAM_PORT}/2015-03-31/functions/{function_name}/invocations'
            req = urllib.request.Request(
                invoke_url,
                data=json.dumps(event).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=900) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            self.send_response(502)
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'SAM invoke failed: {e}'}).encode())
            return
        except Exception as e:
            self.send_response(500)
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        # Forward the Lambda response back to the client
        status = result.get('statusCode', 200)
        resp_headers = result.get('headers', {})
        resp_body = result.get('body', '')

        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        for k, v in resp_headers.items():
            if k.lower().startswith('access-control'):
                continue  # We already set CORS headers
            self.send_header(k, v)
        self.end_headers()
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
