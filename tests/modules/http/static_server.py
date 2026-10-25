#!/usr/bin/env python3
"""Actual static HTTP response witness; optional timing requires an exclusive lease."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report
PAYLOAD = bytes(range(256)) * 16
# All requests use persistent HTTP/1.1. No peer half-close, coroutine suspension,
# TLS or external service is involved. Those remain distinct lifetime gates.
WORKLOADS = [
    ('file', 'GET', '/assets/data.txt', {}, 200, PAYLOAD),
    ('percent-query', 'GET', '/assets/data%2Etxt?version=1', {}, 200, PAYLOAD),
    ('literal-rewrite', 'GET', '/download/data.txt', {}, 200, PAYLOAD),
    ('range', 'GET', '/assets/data.txt', {'Range': 'bytes=17-80'}, 206, PAYLOAD[17:81]),
    ('head', 'HEAD', '/assets/data.txt', {}, 200, b''),
    ('conditional', 'GET', '/assets/data.txt', {'If-Modified-Since': 'Tue, 01 Jan 2030 00:00:00 GMT'}, 304, b''),
    ('index', 'GET', '/assets/index/', {}, 200, b'index fixture'),
    ('autoindex', 'GET', '/assets/list/', {}, 200, None),
    ('missing', 'GET', '/assets/absent.txt', {}, 404, None),
    ('dynamic', 'GET', '/dynamic', {}, 200, b'dynamic fixture'),
]

MULTIPART = {
    'multipart': [(0, 0), (17, 20), (4095, 4095)],
    'multipart-suffix': [(4089, 4095), (17, 20)],
    'multipart-overlap': [(0, 1), (0, 1)],
    'if-range-equal': [(0, 1), (17, 20)],
}
WORKLOADS += [
    ('multipart', 'GET', '/assets/data.txt', {'Range': 'bytes=0-0,17-20,4095-4095'}, 206, None),
    ('multipart-suffix', 'GET', '/assets/data.txt', {'Range': 'bytes=-7,17-20'}, 206, None),
    ('multipart-overlap', 'GET', '/assets/data.txt', {'Range': 'bytes=0-1,0-1'}, 206, None),
    ('skip-unsatisfiable', 'GET', '/assets/data.txt', {'Range': 'bytes=9999-,17-20'}, 206, PAYLOAD[17:21]),
    ('if-range-stale', 'GET', '/assets/data.txt', {'Range': 'bytes=0-1,17-20', 'If-Range': 'Mon, 01 Jan 1990 00:00:00 GMT'}, 200, PAYLOAD),
    ('if-range-equal', 'GET', '/assets/data.txt', {'Range': 'bytes=0-1,17-20', 'If-Range': 'Wed, 01 Jan 2020 00:00:00 GMT'}, 206, None),
]

def multipart_body(boundary, parts):
    return b'\r\n'.join(
        b'--' + boundary + b'\r\nContent-Type: text/plain\r\nContent-Range: bytes ' +
        f'{start}-{end}/{len(PAYLOAD)}'.encode() + b'\r\n\r\n' + PAYLOAD[start:end+1]
        for start, end in parts
    ) + b'\r\n--' + boundary + b'--\r\n'

def request(connection, workload, wire_samples=None):
    name, method, path, headers, status, expected = workload
    previous_socket = connection.sock
    connection.request(method, path, headers={'Host': 'localhost', 'Connection': 'keep-alive', **headers})
    response = connection.getresponse()
    body = response.read()
    if previous_socket is not None and connection.sock is not previous_socket:
        raise AssertionError(f'{name}: keep-alive socket was replaced')
    if response.status != status or expected is not None and body != expected:
        raise AssertionError(f'{name}: status={response.status}, body length={len(body)}')
    if name == 'autoindex' and not all(word in body for word in [b'Index of /assets/list/', b'alpha.txt', b'beta.txt']):
        raise AssertionError('autoindex markup missing expected entries')
    if name == 'missing' and b'404' not in body:
        raise AssertionError('missing response lacks original 404 body')
    if name == 'range' and response.getheader('Content-Range') != 'bytes 17-80/4096':
        raise AssertionError('range metadata')
    if name == 'head' and response.getheader('Content-Length') != '0':
        raise AssertionError('legacy HEAD content length')
    wire_length = len(body)
    boundary = None
    if name in MULTIPART:
        content_type = response.getheader('Content-Type', '')
        prefix = 'multipart/byteranges; boundary='
        if not content_type.startswith(prefix):
            raise AssertionError(f'{name}: multipart content type {content_type!r}')
        boundary = content_type[len(prefix):].encode('ascii')
        if len(boundary) != 38 or not boundary.startswith(b'SwooleBoundary'):
            raise AssertionError(f'{name}: pinned boundary prefix/random-length policy')
        if body != multipart_body(boundary, MULTIPART[name]):
            raise AssertionError(f'{name}: exact multipart boundary/header/payload bytes differ')
        if response.getheader('Content-Length') != str(len(body)):
            raise AssertionError(f'{name}: multipart content length')
        if wire_samples is not None:
            wire_samples.append({'workload': name, 'boundary': boundary.decode('ascii'),
                                 'body_sha256': hashlib.sha256(body).hexdigest(), 'body_length': len(body)})
        # Exact bytes above are verified using the actual random boundary. Only
        # that boundary is canonicalized for comparison between server processes.
        body = multipart_body(b'BOUNDARY', MULTIPART[name])
    # Calendar wall time and the checked random multipart boundary are native;
    # preserve every remaining header byte for parity.
    normalized = [(key.lower(), value) for key, value in response.getheaders() if key.lower() != 'date']
    if boundary is not None:
        normalized = [(key, 'multipart/byteranges; boundary=BOUNDARY' if key == 'content-type' else value) for key, value in normalized]
    return {'status': response.status, 'headers': normalized,
            'body_canonical_sha256' if boundary is not None else 'body_sha256': hashlib.sha256(body).hexdigest(),
            'body_length': wire_length}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--measure', action='store_true', help='Only under an explicitly acknowledged host-exclusive timing lease')
    parser.add_argument('--requests', type=int, default=1000)
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    if args.requests < 1 or args.repeat < 1:
        parser.error('requests/repeat must be positive')
    local = Path(__file__).resolve().parent
    report = {'scope': 'Actual synchronous local HTTP/static PHP server; not suspended-response, TLS or full application parity',
              'measured': args.measure, 'engines': [], 'checks': [], 'trials': [], 'errors': [], 'passed': False}
    engines = parse_engines(args.engine, args.php, args.php_extension)
    reference = None
    try:
        for engine in engines:
            report['engines'].append(engine.metadata())
            with server(engine, local/'static_server.php') as (port, _):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    wire_samples = []
                    outcomes = {workload[0]: request(connection, workload, wire_samples) for workload in WORKLOADS}
                finally:
                    connection.close()
            report['checks'].append({'engine': engine.name, 'outcomes': outcomes, 'multipart_wire_samples': wire_samples})
            if reference is None:
                reference = outcomes
            elif outcomes != reference:
                raise AssertionError(f'{engine.name}: response/header parity differs from first engine')
            write_report(args.output, report)
        if args.measure:
            # Alternate engine order and rotate/reverse workloads to reduce fixed
            # ordering bias. Server startup, warmup and teardown are outside timing.
            for trial in range(args.repeat):
                ordered = engines if trial % 2 == 0 else list(reversed(engines))
                workloads = WORKLOADS[trial % len(WORKLOADS):] + WORKLOADS[:trial % len(WORKLOADS)]
                if trial % 2:
                    workloads = list(reversed(workloads))
                for engine in ordered:
                    with server(engine, local/'static_server.php') as (port, _):
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                        try:
                            for workload in workloads:
                                for _ in range(10):
                                    if request(connection, workload) != reference[workload[0]]:
                                        raise AssertionError('response changed during warmup/timing')
                                begin = time.perf_counter_ns()
                                for _ in range(args.requests):
                                    if request(connection, workload) != reference[workload[0]]:
                                        raise AssertionError('response changed during warmup/timing')
                                elapsed = time.perf_counter_ns() - begin
                                report['trials'].append({'engine': engine.name, 'workload': workload[0], 'trial': trial,
                                                         'requests': args.requests, 'ns_per_request': elapsed / args.requests})
                        finally:
                            connection.close()
                    write_report(args.output, report)
            report['medians_ns_per_request'] = {engine.name: {workload[0]: statistics.median(
                row['ns_per_request'] for row in report['trials'] if row['engine'] == engine.name and row['workload'] == workload[0])
                for workload in WORKLOADS} for engine in engines}
        report['passed'] = True
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']), 'measured': args.measure, 'errors': report['errors']}))
    return 0 if report['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
