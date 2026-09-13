"""Exercise the public HTTP contract using synthetic data and no paid model calls."""
import argparse
import csv
import io
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--password-file')
    parser.add_argument('--health-only', action='store_true')
    args = parser.parse_args()
    password = Path(args.password_file).read_text().strip() if args.password_file else ''

    def request(path, body=None, content_type='application/json', authenticated=True):
        headers = {'Content-Type': content_type}
        if authenticated and password:
            headers['X-Access-Key'] = password
        with urlopen(Request(urljoin(args.base_url, path), body, headers), timeout=30) as response:
            return response.read(), response.headers

    raw, _ = request('/health', authenticated=False)
    assert json.loads(raw).get('status') == 'ok'
    raw, _ = request('/api/config', authenticated=False)
    assert json.loads(raw)['demoMode'] is True, 'Smoke test requires explicit demo mode'
    raw, headers = request('/', authenticated=False)
    assert b'<app-root>' in raw
    assert headers.get('X-Content-Type-Options') == 'nosniff'
    assert headers.get('Content-Security-Policy')
    if args.health_only:
        print('Container health, static UI, demo configuration and response headers passed.')
        return
    if not password:
        raise SystemExit('--password-file is required for the complete contract test')
    raw, _ = request('/api/auth/validate', json.dumps({'password': password}).encode(), authenticated=False)
    assert json.loads(raw)['valid'] is True
    boundary = uuid.uuid4().hex
    comments = 'id,comment\n' + ''.join(f'{i},Synthetic public comment {i}\n' for i in range(1, 51))
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.csv"\r\n'
            f'Content-Type: text/csv\r\n\r\n{comments}\r\n--{boundary}--\r\n').encode()
    raw, _ = request('/api/upload', body, f'multipart/form-data; boundary={boundary}')
    uploaded = json.loads(raw)
    assert uploaded['rowCount'] == 50
    payload = {'fileId': uploaded['fileId'], 'selectedCommentColumn': 'comment', 'contextDescription': 'Synthetic workflow check.', 'analysisColumns': [
        {'name': 'Position', 'type': 'categorized', 'instructions': 'Choose the best label.',
         'options': [{'value': 'Support', 'description': 'Supports the proposal'},
                     {'value': 'Concern', 'description': 'Expresses concern'}]}]}
    raw, _ = request('/api/process', json.dumps(payload).encode())
    job = json.loads(raw)['jobId']

    def wait_status(expected):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            raw, _ = request(f'/api/status/{job}')
            status = json.loads(raw)
            if status['status'] == expected:
                return status
            assert status['status'] != 'failed', 'Synthetic job failed'
            time.sleep(0.2)
        raise AssertionError(f'Timed out waiting for {expected}')

    preview = wait_status('preview_ready')
    assert len(preview['previewRows']) == 20
    assert all('Demo mode' in row['_analysis_notice'] for row in preview['previewRows'])
    request(f'/api/process/{job}/preview-confirm', b'{}')
    try:
        request(f'/api/process/{job}/preview-confirm', b'{}')
        raise AssertionError('Duplicate confirmation was accepted')
    except HTTPError as error:
        assert error.code == 409
    status = wait_status('completed')
    assert status['completedRows'] == 50
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        raw, _ = request(f'/api/results/{job}')
        results = json.loads(raw)
        if results['aggregateAnalysis']:
            break
        assert results.get('analysisStatus') != 'failed'
        time.sleep(0.2)
    assert 'Demo mode' in results['aggregateAnalysis']
    download = urljoin(args.base_url, results['downloadUrl'])
    assert urlsplit(download).netloc == urlsplit(args.base_url).netloc
    raw, _ = request(download, authenticated=False)
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    assert [row['id'] for row in rows] == [str(i) for i in range(1, 51)]
    assert all(row['Position'] == 'Support' for row in rows)
    assert all('Demo mode' in row['_analysis_notice'] for row in rows)
    raw, _ = request(f'/api/dashboard/{job}', json.dumps({'prompt': 'Summarize the positions.'}).encode())
    dashboard = json.loads(raw)
    assert isinstance(dashboard['charts'], list) and 'Demo mode' in dashboard['narrative']
    print('HTTP upload, 20-row preview, confirmation, duplicate rejection, 50 ordered rows, signed download, summary and dashboard passed.')


if __name__ == '__main__':
    main()
