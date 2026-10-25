#!/usr/bin/env python3
"""Actual PHP Response chunk, trailer and split-send boundary wire consumers."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report


def request(port, path, body):
    with socket.create_connection(('127.0.0.1', port), timeout=5) as connection:
        head = (f'POST {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n').encode()
        connection.sendall(head + body)
        received = bytearray()
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            received.extend(chunk)
            assert len(received) < 1048576
    head, wire_body = bytes(received).split(b'\r\n\r\n', 1)
    lines = head.decode('latin1').split('\r\n')
    headers = [line.split(': ', 1) for line in lines[1:]]
    headers = [(key.lower(), value) for key, value in headers if key.lower() != 'date']
    values = dict(headers)
    trailers = []
    chunks = []
    if values.get('transfer-encoding') == 'chunked':
        remaining = wire_body
        while True:
            line, remaining = remaining.split(b'\r\n', 1)
            length = int(line, 16)
            if not length:
                for line in remaining.split(b'\r\n'):
                    if line:
                        key, value = line.decode('latin1').split(': ', 1)
                        trailers.append((key.lower(), value))
                break
            chunks.append(remaining[:length])
            assert remaining[length:length + 2] == b'\r\n'
            remaining = remaining[length + 2:]
        decoded = b''.join(chunks)
    else:
        assert len(wire_body) == int(values['content-length'])
        decoded = wire_body
    return {'status': lines[0], 'headers': headers, 'trailers': trailers,
            'chunk_lengths': [len(chunk) for chunk in chunks],
            'wire_sha256': hashlib.sha256(wire_body).hexdigest()}, decoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if len(engines) < 2 or engines[0].name != 'upstream':
        parser.error('First engine upstream=PATH plus candidate engine(s) required')
    fixture = Path(__file__).with_suffix('.php')
    report = {'scope': __doc__, 'limitations': 'Actual successful native IO and empty-write warnings; no forced socket failure, cancellation, HTTP2, fatal bailout or GC proof.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    lengths = [0, 1, 17, 16383, 16384, 16385, 32768]
    paths = ['/end', '/write', '/chunks', '/end-data', '/trailers']
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for mode in ['normal', 'normal-coroutine', 'coroutine']:
                with server(engine, fixture, {'HTTPBINDINGS_MODE': mode}) as (port, proc):
                    for length in lengths:
                        body = bytes(range(256)) * (length // 256) + bytes(range(length % 256))
                        for path in paths:
                            observed, decoded = request(port, path, body)
                            assert observed['status'] == 'HTTP/1.1 201 Created'
                            if path == '/end':
                                assert decoded == body and not observed['chunk_lengths']
                            elif path == '/end-data':
                                assert decoded == b'prefix' + body
                            else:
                                prefix, meta = decoded.rsplit(b'|meta=', 1)
                                assert prefix == body
                                data = json.loads(meta)
                                expected = [bool(length)] * max(1, (length + 16) // 17) if path == '/chunks' else [bool(length)]
                                assert data['results'] == expected
                                assert len(data['warnings']) == (0 if length else 1)
                                if length == 0:
                                    assert 'the data sent must not be empty' in data['warnings'][0]
                                if path == '/trailers':
                                    assert observed['trailers'] == [('x-test', 'space + tilde~'), ('x-empty', '')]
                            key = (mode, length, path)
                            if index == 0:
                                baseline[key] = observed
                            assert observed == baseline[key], (key, observed, baseline[key])
                            report['cases'].append({'engine': engine.name, 'mode': mode, 'length': length, 'path': path, 'observed': observed})
                    if mode == 'coroutine':
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                        connection.request('GET', '/stop')
                        response = connection.getresponse()
                        assert response.read() == b'stopped'
                        connection.close()
                        proc.wait(timeout=5)
                        assert proc.returncode == 0
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['passed'] = not report['errors'] and len(report['cases']) == len(lengths) * len(paths) * 3 * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
