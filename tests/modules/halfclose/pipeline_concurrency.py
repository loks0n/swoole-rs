#!/usr/bin/env python3
"""Preserve pipelined coroutine concurrency; optional early FIN remains an explicit probe."""
import argparse
import http.client
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, server, write_report
from tests.modules.halfclose.gate import require

class PipelineSocket:
    class Buffer(io.BytesIO):
        def close(self):
            pass
    def __init__(self, data):
        self.buffer = self.Buffer(data)
    def makefile(self, mode):
        return self.buffer

def run(engine, early_fin, row):
    with tempfile.TemporaryDirectory(prefix='pipeline-concurrency-') as directory:
        events = Path(directory) / 'events.json'
        with server(engine, Path(__file__).with_suffix('.php'), {'TEST_EVENTS': str(events)}) as (port, proc):
            with socket.create_connection(('127.0.0.1', port), timeout=5) as connection:
                connection.sendall(b'GET /first HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n'
                                   b'GET /second HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                if early_fin:
                    connection.shutdown(socket.SHUT_WR)
                parts = []
                while True:
                    part = connection.recv(8192)
                    if not part:
                        break
                    parts.append(part)
            raw = b''.join(parts)
            row.update(bytes=len(raw), responses=[])
            deadline = time.monotonic() + 3
            while not events.exists() or not json.loads(events.read_text()).get('second_finished'):
                require(time.monotonic() < deadline, 'response lifecycle did not complete')
                time.sleep(.01)
            row['events'] = json.loads(events.read_text())
            require(row['events'].get('second_before_first_finished'), 'pipeline was serialized across suspended first callback')
            require(row['events'].get('second_saw_first'), 'second callback did not observe first request')
            require(row['events'].get('first_saw_second'), 'first callback could not await second request')
            replies = PipelineSocket(raw)
            for expected in [b'first:ok', b'second:ok']:
                reply = http.client.HTTPResponse(replies)
                reply.begin()
                body = reply.read()
                row['responses'].append({'status': reply.status, 'body': body.decode()})
                require(reply.status == 200 and body == expected, f'pipeline response mismatch: {row}')
            require(not replies.buffer.read(1), 'unexpected trailing response bytes')
            require(proc.poll() is None, 'server exited')
            return row

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', action='append', required=True)
    p.add_argument('--php', default='php')
    p.add_argument('--php-extension', action='append', default=[])
    p.add_argument('--probe-early-fin', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = {'scope': 'Actual PHP pipeline concurrency; early FIN is an explicit unsupported probe, never counted passed on failure',
         'early_fin': a.probe_early_fin, 'engines': [], 'results': []}
    for e in parse_engines(a.engine, a.php, a.php_extension):
        r['engines'].append(e.metadata())
        row = {'engine': e.name, 'passed': False}
        try:
            run(e, a.probe_early_fin, row)
            row['passed'] = True
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        r['results'].append(row)
        write_report(a.output, r)
        print(json.dumps(row), flush=True)
    return int(any(not row['passed'] for row in r['results']))

if __name__ == '__main__':
    raise SystemExit(main())
