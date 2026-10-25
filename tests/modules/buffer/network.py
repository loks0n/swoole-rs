#!/usr/bin/env python3
"""Verify ordered streaming, queued output, sendfile offsets and keep-alive."""
import argparse
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, server, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/buffer-network.json'))
    args = parser.parse_args()
    block = bytes(range(256)) * 256
    payload = b''.join(struct.pack('>I', i) + block[4:] for i in range(64))
    fixture = Path(__file__).with_name('server.php')
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'engines': [], 'results': []}
    for engine in parse_engines(args.engine, args.php):
        report['engines'].append(engine.metadata())
        row = {'engine': engine.name, 'passed': False, 'responses': []}
        try:
            with server(engine, fixture) as (port, process):
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                try:
                    for path, expected in [('/stream', payload), ('/file', payload[13:-14]), ('/', b'ok')]:
                        conn.request('GET', path)
                        # Let the bounded server queue fill before receiving the body.
                        time.sleep(.1)
                        response = conn.getresponse()
                        body = bytearray()
                        while chunk := response.read(16384):
                            body.extend(chunk)
                        if response.status != 200 or body != expected:
                            raise AssertionError(f'{path}: status={response.status}, bytes={len(body)}')
                        row['responses'].append({'path': path, 'bytes': len(body)})
                        if conn.sock is None:
                            raise AssertionError('keep-alive connection closed')
                        if path == '/stream':
                            conn.request('GET', '/queue')
                            observed = conn.getresponse()
                            info = json.loads(observed.read())
                            queued = info.get('send_queued_bytes', 0)
                            if observed.status != 200 or queued <= 0:
                                raise AssertionError(f'output queue was not exercised: {info}')
                            row['observed_queued_bytes'] = queued
                    cancelled = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                    try:
                        cancelled.request('GET', '/stream')
                        time.sleep(.05)
                        partial = cancelled.getresponse()
                        if partial.status != 200 or len(partial.read(1024)) != 1024:
                            raise AssertionError('partial response failed')
                    finally:
                        cancelled.close()
                    time.sleep(.05)
                    conn.request('GET', '/')
                    healthy = conn.getresponse()
                    if healthy.status != 200 or healthy.read() != b'ok':
                        raise AssertionError('server failed after cancelled response')
                    row['healthy_after_cancel'] = True
                    if process.poll() is not None:
                        raise AssertionError('server exited')
                finally:
                    conn.close()
            row['passed'] = True
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        report['results'].append(row)
        write_report(args.output, report)
        print(engine.name, row, flush=True)
    return int(any(not row['passed'] for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
