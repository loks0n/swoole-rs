#!/usr/bin/env python3
"""Actual PHP multipart streaming witness above the native request-buffer limit."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report
BOUNDARY = 'swoole-rust-normal-upload'
PAYLOAD = bytes(range(256)) * 384

def upload(files):
    body = bytearray(f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="meta"\r\n\r\nvalue\r\n'.encode())
    expected = {'post': {'meta': 'value'}, 'files': {}}
    for field, payload in files:
        name = field + '.bin'
        body.extend(f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
        body.extend(payload)
        body.extend(b'\r\n')
        expected['files'][field] = {'name': name, 'type': 'application/octet-stream', 'size': len(payload),
                                    'error': 0, 'sha256': hashlib.sha256(payload).hexdigest()}
    body.extend(f'--{BOUNDARY}--\r\n'.encode())
    assert len(body) > 32 * 1024
    return bytes(body), expected

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = Path(__file__).with_name('static_server.php')
    report = {'scope': 'Actual synchronous PHP successful multipart uploads above32KiB request limit/below128KiB per-file limit; not suspended/TLS/full API coverage',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    try:
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            report['engines'].append(engine.metadata())
            with server(engine, fixture) as (port, _):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    near_boundary = (b'\r\n--swoole-rust-normal-uploaX\r\n' + bytes(range(256))) * 256
                    for name, files in [('single', [('sample', PAYLOAD)]),
                                        ('two-files', [('sample', PAYLOAD), ('second', PAYLOAD[:8192])]),
                                        # Combined size exceeds the per-file limit: reset must occur.
                                        ('two-large-files', [('sample', PAYLOAD), ('second', PAYLOAD)]),
                                        ('empty-then-large', [('empty', b''), ('sample', PAYLOAD)]),
                                        ('large-then-empty', [('sample', PAYLOAD), ('empty', b'')]),
                                        ('duplicate-field', [('sample', PAYLOAD), ('sample', PAYLOAD[:8192])]),
                                        ('near-boundary-binary', [('sample', near_boundary)])]:
                        body, expected = upload(files)
                        previous_socket = connection.sock
                        connection.request('POST', '/upload', body=body,
                                           headers={'Host': 'localhost', 'Connection': 'keep-alive',
                                                    'Content-Type': 'multipart/form-data; boundary=' + BOUNDARY})
                        response = connection.getresponse()
                        raw = response.read()
                        if previous_socket is not None and connection.sock is not previous_socket:
                            raise AssertionError(f'{engine.name}/{name}: keep-alive socket was replaced')
                        if response.status != 200 or json.loads(raw) != expected:
                            raise AssertionError(f'{engine.name}/{name}: status={response.status}, body={raw!r}')
                        report['cases'].append({'engine': engine.name, 'case': name, 'request_length': len(body), 'outcome': expected})
                finally:
                    connection.close()
            write_report(args.output, report)
        report['passed'] = True
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
