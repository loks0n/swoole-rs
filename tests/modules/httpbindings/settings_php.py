#!/usr/bin/env python3
"""Actual coroutine HTTP startup settings, alias precedence and native reentry."""
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
    fixture = Path(__file__).with_suffix('.php')
    configs = [({}, {}), ({'upload_tmp_dir': True}, {})]
    for key in ['http_parse_cookie', 'http_parse_post', 'http_parse_files']:
        for value in [False, True, None, 0, '0', '1']:
            configs.append(({key: value}, {}))
    for key in ['http_compression_level', 'compression_level', 'http_gzip_level']:
        for value in [False, None, -1, 0, 9, 256]:
            configs.append(({'http_compression': True, 'http_compression_min_length': 0, key: value}, {}))
    for value in [False, None, 1]:
        configs.append(({'http_compression': True, 'http_compression_min_length': 0,
                         'http_compression_level': value, 'compression_level': 9, 'http_gzip_level': 1}, {}))
    for key in ['http_compression_min_length', 'compression_min_length']:
        for value in [0, 999999, None]:
            configs.append(({'http_compression': True, key: value}, {}))
    for key in ['http_compression_types', 'compression_types']:
        for value in [[], ['application/json'], ['text/plain'], None]:
            configs.append(({'http_compression': True, 'http_compression_min_length': 0, key: value}, {}))
    configs.append(({'http_compression': True, 'http_compression_min_length': 0,
                     'http_compression_types': [], 'compression_types': ['application/json']}, {}))
    boundary = 'settings-boundary'
    multipart = (f'--{boundary}\r\nContent-Disposition: form-data; name="field"\r\n\r\nvalue\r\n'
                 f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="a.bin"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n').encode() + bytes(range(256)) + f'\r\n--{boundary}--\r\n'.encode()
    bodies = [('form', b'one=a+b&two=%00binary', 'application/x-www-form-urlencoded'),
              ('multipart', multipart, f'multipart/form-data; boundary={boundary}')]
    report = {'scope': __doc__, 'limitations': 'Valid public settings through real native Zend/FS/zlib effects; no actual fatal bailout, allocation-fault, GC or optional codec proof.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for number, (settings, _) in enumerate(configs):
                with server(engine, fixture, {'HTTPBINDINGS_SETTINGS': json.dumps(settings)}) as (port, proc):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                    for kind, body, content_type in bodies:
                        connection.request('POST', '/', body=body, headers={'Host': 'localhost',
                            'Connection': 'keep-alive', 'Cookie': 'one=1; two=space+plus',
                            'Accept-Encoding': 'gzip', 'Content-Type': content_type})
                        response = connection.getresponse()
                        raw = response.read()
                        encoding = response.getheader('Content-Encoding')
                        decoded = gzip.decompress(raw) if encoding == 'gzip' else zlib.decompress(raw, -15) if encoding == 'deflate' else raw
                        data = json.loads(decoded)
                        assert response.status == 200 and data['content'] == body.hex()
                        if settings.get('http_parse_cookie') in [False, 0, '0'] and settings.get('http_parse_cookie') is not None:
                            assert data['cookie'] == []
                        elif settings.get('http_parse_cookie') is True:
                            assert data['cookie']['one'] == '1'
                        if kind == 'form' and settings.get('http_parse_post') in [False, 0, '0'] and settings.get('http_parse_post') is not None:
                            assert data['post'] == []
                        if kind == 'multipart':
                            # Pinned multipart parser still publishes fields with parse_post=false.
                            assert data['post']['field'] == 'value'
                            assert data['files']['upload']['hash'] == hashlib.sha256(bytes(range(256))).hexdigest()
                        for type_key in ['http_compression_types', 'compression_types']:
                            if type_key in settings and settings[type_key] is not None:
                                assert encoding == ('gzip' if 'application/json' in settings[type_key] else None)
                                break
                        if settings.get('upload_tmp_dir') is True:
                            assert data['events'] == ['upload-string', '/nested']
                        observed = {'body': data, 'encoding': encoding, 'wire_sha256': hashlib.sha256(raw).hexdigest()}
                        key = (number, kind)
                        if index == 0:
                            baseline[key] = observed
                        assert observed == baseline[key], (settings, kind, observed, baseline[key])
                        report['cases'].append({'engine': engine.name, 'settings': settings, 'body_kind': kind, 'observed': observed})
                    connection.request('GET', '/stop')
                    response = connection.getresponse()
                    assert response.read() == b'stopped'
                    connection.close()
                    proc.wait(timeout=5)
                    assert proc.returncode == 0
        def wire(settings, kind):
            number = next(i for i, (value, _) in enumerate(configs) if value == settings)
            return baseline[(number, kind)]['wire_sha256']
        common = {'http_compression': True, 'http_compression_min_length': 0}
        for kind, _, _ in bodies:
            assert wire({**common, 'http_compression_level': False, 'compression_level': 9, 'http_gzip_level': 1}, kind) == wire({**common, 'http_compression_level': 0}, kind)
            assert wire({**common, 'http_compression_level': None, 'compression_level': 9, 'http_gzip_level': 1}, kind) == wire({**common, 'compression_level': 9}, kind)
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['passed'] = not report['errors'] and len(report['cases']) == len(configs) * len(bodies) * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
