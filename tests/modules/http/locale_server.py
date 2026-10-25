#!/usr/bin/env python3
"""Actual static HTTP consumers under selected native LC_CTYPE profiles."""
import argparse
import ctypes
import http.client
import json
import locale
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report

LOCALES = ['C', 'C.UTF-8', 'en_US.ISO8859-1', 'tr_TR.ISO8859-9', 'tr_TR.UTF-8']
CASES = [('binary-location', b'/\xc3\x80/data.txt', b'/\xe3\x80', b'static-high'),
         ('ascii-i', b'/I/data.txt', b'/i', b'static-ascii')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = Path(__file__).with_suffix('.php')
    libc = ctypes.CDLL(None)
    libc.strncasecmp.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
    libc.strncasecmp.restype = ctypes.c_int
    report = {'scope': 'Actual private PHP static-handler locale callers; expected selection uses the same unsanitized POSIX libc prefix helper as pinned native. No original assertions edited, no performance/activation claim.',
              'engines': [], 'results': [], 'passed': False}
    previous = locale.setlocale(locale.LC_CTYPE)
    try:
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            report['engines'].append(engine.metadata())
            for name in LOCALES:
                try:
                    locale.setlocale(locale.LC_CTYPE, name)
                except locale.Error:
                    report['results'].append({'engine': engine.name, 'locale': name,
                                              'status': 'unsupported', 'detail': 'Native locale unavailable'})
                    continue
                try:
                    with server(engine, fixture, {'HTTP_LOCALE': name}) as (port, _):
                        for case, path, location, payload in CASES:
                            selected = libc.strncasecmp(path, location, len(location)) == 0
                            # Pinned PHP fallback rejects raw high-byte targets;
                            # static selection runs before that separate parser.
                            status = 400 if case == 'binary-location' and not selected else 200
                            expected = payload if selected else b'' if status == 400 else b'dynamic'
                            with socket.create_connection(('127.0.0.1', port), timeout=5) as connection:
                                connection.sendall(b'GET ' + path + b' HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                                response = http.client.HTTPResponse(connection)
                                response.begin()
                                body = response.read()
                                matched = response.status == status and body == expected
                                report['results'].append({'engine': engine.name, 'locale': name,
                                    'case': case, 'request_path_hex': path.hex(), 'location_hex': location.hex(),
                                    'native_prefix_selected': selected, 'expected': expected.decode(),
                                    'expected_http_status': status,
                                    'http_status': response.status, 'body_hex': body.hex(),
                                    'status': 'passed' if matched else 'failed'})
                except Exception as error:
                    report['results'].append({'engine': engine.name, 'locale': name, 'status': 'failed',
                                              'detail': f'{type(error).__name__}: {error}'})
                write_report(args.output, report)
    finally:
        locale.setlocale(locale.LC_CTYPE, previous)
    report['passed'] = bool(report['results']) and not any(row['status'] == 'failed' for row in report['results'])
    report['all_requested_profiles_passed'] = report['passed'] and all(row['status'] == 'passed' for row in report['results'])
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'results': len(report['results']),
                      'failed': sum(row['status'] == 'failed' for row in report['results']),
                      'unsupported': sum(row['status'] == 'unsupported' for row in report['results'])}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
