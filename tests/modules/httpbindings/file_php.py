#!/usr/bin/env python3
"""Actual private-file Response sendfile ranges, MIME and early-error consumers."""
import argparse
import http.client
import json
from pathlib import Path
import sys
import tempfile
import time
from emission_php import request
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
    cases = []
    for header in [0, 1, 2]:
        for kind in ['file', 'link']:
            for offset, length in [(0, 0), (0, 1), (1, 17), (16383, 2), (32768, 0), (32769, 0), (0, 32769), (32767, 1)]:
                cases.append({'kind': kind, 'offset': offset, 'length': length, 'header': header, 'chunk': False})
        for offset, length in [(0, 0), (1, 0), (0, 1)]:
            cases.append({'kind': 'empty', 'offset': offset, 'length': length, 'header': header, 'chunk': False})
        for kind in ['missing', 'directory', 'empty-name']:
            cases.append({'kind': kind, 'offset': 0, 'length': 0, 'header': header, 'chunk': False})
    cases.append({'kind': 'file', 'offset': 0, 'length': 1, 'header': 0, 'chunk': True})
    report = {'scope': __doc__, 'limitations': 'Bounded valid/nonnegative ranges and private files only; signed edge ranges use native-body numeric gate. No forced backend failure, callback teardown, HTTP2, GC/bailout or performance proof.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    payload = bytes(range(256)) * 128
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for mode in ['normal', 'normal-coroutine', 'coroutine']:
                with tempfile.TemporaryDirectory(prefix='swr-file-audit-') as audit:
                    with server(engine, fixture, {'HTTPBINDINGS_MODE': mode, 'HTTPBINDINGS_AUDIT': audit}) as (port, proc):
                        for number, case in enumerate(cases):
                            observed, body = request(port, '/', json.dumps({**case, 'id': number}).encode())
                            output = Path(audit) / (str(number) + '.json')
                            deadline = time.monotonic() + 2
                            while not output.is_file() and time.monotonic() < deadline:
                                time.sleep(.005)
                            data = json.loads(output.read_text())
                            observed['native'] = data
                            assert observed['status'] == 'HTTP/1.1 201 Created'
                            if data['result']:
                                source = payload if case['kind'] in ['file', 'link'] else b''
                                length = case['length'] or len(source) - case['offset']
                                assert body == source[case['offset']:case['offset'] + length]
                                assert not data['warnings'] and not data['writable_after_sendfile']
                                assert not observed['chunk_lengths']
                            else:
                                assert data['warnings'] and body == (b'prefixfailure' if case['chunk'] else b'failure')
                            key = (mode, number)
                            if index == 0:
                                baseline[key] = observed
                            assert observed == baseline[key], (key, case, observed, baseline[key])
                            report['cases'].append({'engine': engine.name, 'mode': mode, 'case': case, 'observed': observed})
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
    report['passed'] = not report['errors'] and len(report['cases']) == len(cases) * 3 * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
