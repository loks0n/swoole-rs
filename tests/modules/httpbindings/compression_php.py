#!/usr/bin/env python3
"""Actual PHP request negotiation and native codec/Response consumers."""
import argparse
import gzip
import hashlib
import http.client
import json
from pathlib import Path
import sys
import zlib
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
    fixture = Path(__file__).with_name('server_php.php')
    report = {'scope': __doc__, 'limitations': 'Actual enabled-zlib native effects; no actual enabled Brotli/Zstd or codec conversion/performance claim.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    cases = [('identity', None), ('gzip', 'gzip'), ('deflate', 'deflate'), ('GZIP', None),
             ('gzip;q=0', 'gzip'), ('x-gzip-tail', 'gzip'), ('deflate,gzip', 'gzip'),
             ('deflate;q=0', 'deflate'), ('', None)]
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for mode in ['normal', 'coroutine']:
                for level in [-1, 0, 1, 9, 10, 127, 128, 255, 256]:
                    with server(engine, fixture, {'HTTPBINDINGS_MODE': mode, 'HTTPBINDINGS_COMPRESSION': '1', 'HTTPBINDINGS_COMPRESSION_LEVEL': str(level)}) as (port, _):
                        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                        for accepted, expected in cases:
                            body = bytes(range(256)) * 16
                            previous = connection.sock
                            connection.request('POST', '/compression', body=body, headers={'Host': 'localhost',
                                'Accept-Encoding': accepted, 'Connection': 'keep-alive', 'Content-Type': 'application/octet-stream'})
                            response = connection.getresponse()
                            raw = response.read()
                            encoding = response.getheader('Content-Encoding')
                            assert encoding == expected, (accepted, encoding, expected)
                            decoded = gzip.decompress(raw) if encoding == 'gzip' else zlib.decompress(raw, -15) if encoding == 'deflate' else raw
                            data = json.loads(decoded)
                            assert response.status == 207 and data['content'] == body.hex() and data['rawContent'] == body.hex()
                            assert previous is None or previous is connection.sock
                            observed = {'status': response.status, 'headers': [(k.lower(), v) for k, v in response.getheaders() if k.lower() != 'date'],
                                        'wire_sha256': hashlib.sha256(raw).hexdigest(), 'decoded_sha256': hashlib.sha256(decoded).hexdigest()}
                            if index == 0:
                                baseline[(mode, level, accepted)] = observed
                            assert observed == baseline[(mode, level, accepted)], (accepted, observed, baseline[(mode, level, accepted)])
                            report['cases'].append({'engine': engine.name, 'mode': mode, 'level': level, 'accepted': accepted, 'observed': observed})
                        connection.close()
            for mode in ['normal', 'coroutine']:
                for left, right in [(-1, 0), (10, 9), (127, 9), (128, 255), (255, 256)]:
                    assert baseline[(mode, left, 'gzip')]['wire_sha256'] == baseline[(mode, right, 'gzip')]['wire_sha256'], (mode, left, right)
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['passed'] = not report['errors'] and len(report['cases']) == 18 * len(cases) * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
