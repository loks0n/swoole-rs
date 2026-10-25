#!/usr/bin/env python3
"""Real PHP normal receive, coroutine route and Request/Response consumers."""
import argparse
import http.client
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report


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
    report = {'scope': __doc__, 'limitations': 'No queue-custody, allocator fault, cancellation, TLS, HTTP2, GC or full API coverage claim.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for mode in ['normal', 'normal-coroutine', 'coroutine']:
                with server(engine, fixture, {'HTTPBINDINGS_MODE': mode}) as (port, proc):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                    for path in ['/', '/alpha', '/ALPHA/tail', '/post?x=1&x=2&space=a+b', '/unmatched']:
                        for kind, body, content_type in [('empty', b'', 'text/plain'),
                            ('form', b'one=a+b&one=last&two=%00x', 'application/x-www-form-urlencoded'),
                            ('binary', bytes(range(256)) * 8, 'application/octet-stream')]:
                            connection.request('POST', path, body=body, headers={
                                'Host': 'localhost', 'Connection': 'keep-alive', 'Content-Type': content_type,
                                'Cookie': 'one=1; two=space+plus; three=%00binary', 'X-Custom': 'value'})
                            response = connection.getresponse()
                            data = json.loads(response.read())
                            # Transport port is deliberately absent from fixture output.
                            observed = {'status': response.status, 'reason': response.reason,
                                'headers': [(k.lower(), v) for k, v in response.getheaders() if k.lower() != 'date'],
                                'body': data}
                            route = 'normal' if mode != 'coroutine' else '/Alpha' if path.lower().startswith('/alpha') else '/post' if path.startswith('/post') else '/'
                            assert response.status == 207 and data['route'] == route, observed
                            assert data['content'] == body.hex() and data['rawContent'] == body.hex(), observed
                            assert data['method'] == 'POST' and data['cookie']['one'] == '1', observed
                            assert response.getheader('X-Mixed-Key') == 'native-response', observed
                            key = f'{mode}/{path}/{kind}'
                            if index == 0:
                                baseline[key] = observed
                            assert observed == baseline[key], (key, observed, baseline[key])
                            report['cases'].append({'engine': engine.name, 'case': key, 'observed': observed})
                    if mode == 'coroutine':
                        connection.request('GET', '/stop')
                        response = connection.getresponse()
                        assert response.read() == b'stopped'
                        proc.wait(timeout=5)
                        assert proc.returncode == 0, proc.returncode
                    connection.close()
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['passed'] = not report['errors'] and len(report['cases']) == 45 * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
