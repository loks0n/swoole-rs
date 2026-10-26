#!/usr/bin/env python3
"""Run pinned set_basic_auth.phpt unchanged against a local HTTPBin fixture.

The original test already supports HTTPBIN_SERVER_HOST/PORT environment values.
Only that documented fixture location is changed; original assertions, expected
output, skip decisions and PHP's official runner remain intact.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated

from tools.build_upstream import COMMIT as PIN
CASE = 'tests/swoole_http_client_coro/set_basic_auth.phpt'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    requests = []

    class HttpBin(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parts = self.path.split('/')
            valid_path = len(parts) == 4 and parts[1] == 'basic-auth'
            expected = 'Basic ' + base64.b64encode(':'.join(unquote(p) for p in parts[2:]).encode()).decode()
            valid = valid_path and self.headers.get('Authorization') == expected
            requests.append({'valid_authorization': valid})
            self.send_response(200 if valid else 401)
            self.send_header('Content-Length', '0')
            self.end_headers()

        def log_message(self, *_):
            pass

    with http.server.HTTPServer(('127.0.0.1', 0), HttpBin) as fixture, tempfile.TemporaryDirectory(prefix='swr-auth-original-') as temporary:
        manifest = Path(temporary) / 'manifest.json'
        original = subprocess.check_output(['git', '-C', str(args.source), 'cat-file', 'blob', PIN + ':' + CASE], timeout=15)
        manifest.write_text(json.dumps({'commit': PIN, 'tests': [{'path': CASE, 'sha256': hashlib.sha256(original).hexdigest(),
                              'module': 'base64', 'requires': ['upstream_test_bootstrap', 'coroutine_http_client']}]}))
        command = [sys.executable, str(ROOT / 'corpus/upstream/run.py'), '--source', str(args.source),
                   '--manifest', str(manifest), '--php', args.php, '--output', str(args.output), '--require-all']
        for engine in args.engine:
            command.extend(['--engine', engine])
        for extension in args.php_extension:
            command.extend(['--php-extension', extension])
        thread = threading.Thread(target=fixture.serve_forever)
        thread.start()
        try:
            # Upstream's config treats GITHUB_ACTIONS as its own CI and points at an httpbin
            # service container instead of HTTPBIN_SERVER_HOST; ours has no such service.
            env = {key: value for key, value in os.environ.items() if key != 'GITHUB_ACTIONS'}
            result = run_isolated(command, timeout=180, env={**env, 'HTTPBIN_SERVER_HOST': '127.0.0.1',
                                                          'HTTPBIN_SERVER_PORT': str(fixture.server_port)})
        finally:
            fixture.shutdown()
            thread.join()
        # Keep the official report even on failure, plus the fixture observations.
        observed = {'argv': command, 'stdout': result.stdout, 'stderr': result.stderr,
                   'returncode': result.returncode, 'requests': requests}
        args.output.with_suffix('.fixture.json').write_text(json.dumps(observed, indent=2) + '\n')
        print(result.stdout, end='')
        result.check_returncode()
        assert len(requests) == len(args.engine) and all(r['valid_authorization'] for r in requests)


if __name__ == '__main__':
    main()
