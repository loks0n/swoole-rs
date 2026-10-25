#!/usr/bin/env python3
"""Pinned Swoole malformed/control/aggregate network-policy compatibility gate."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.run import WebSocket, expect
from tools.harness import ROOT, parse_engines, request, server, write_report
from close_probe import frame

from tools.build_upstream import COMMIT as PIN


def wire(payload, opcode, final=True, masked=True):
    if masked:
        return frame(payload, opcode, final)
    size = len(payload)
    header = bytes([(0x80 if final else 0) | opcode])
    return header + (bytes([size]) if size < 126 else b'\x7e' + struct.pack('!H', size)) + payload


def scenarios():
    rows = [('unexpected-continuation', frame(b'orphan', opcode=0), None),
            ('second-fragment-start', frame(b'first', final=False) + frame(b'second', final=False), None),
            ('fragmented-ping-permitted', frame(b'P', opcode=9, final=False), (b'\x8a\x01', b'P'))]
    # Pinned policy compares total frame bytes with 127, not payload with 125.
    for masked, lengths in [(True, [120, 121, 125, 126]), (False, [124, 125, 126])]:
        for opcode in [9, 10]:
            for length in lengths:
                payload = b'c' * length
                accepted = length + (6 if masked else 2) < 127 and length < 126
                response = (bytes([0x8a, length]), payload) if opcode == 9 and accepted else () if accepted else None
                rows.append((f'{"masked" if masked else "unmasked"}-{"ping" if opcode == 9 else "pong"}-{length}',
                             wire(payload, opcode, masked=masked), response))
    for total in [65535, 65536, 65537]:
        payload = b'a' * 32768 + b'b' * (total - 32768)
        rows.append((f'fragment-aggregate-{total}', frame(payload[:32768], final=False) + frame(payload[32768:], opcode=0),
                     ('echo', payload) if total <= 65536 else None))
    return rows


def run_case(port, name, data, expected):
    client = WebSocket(port)
    row = {'case': name, 'sent_bytes': len(data),
           'expected': 'connection-terminated' if expected is None else 'accepted', 'passed': False}
    try:
        client.socket.settimeout(2)
        client.socket.sendall(data)
        if expected is None:
            try:
                expect(client.socket.recv(1), b'')
                row['observed'] = 'eof'
            except ConnectionResetError:
                row['observed'] = 'reset'
        else:
            if expected and expected[0] == 'echo':
                expect(client.receive(), expected[1])
            elif expected:
                expect(client.read(2), expected[0])
                expect(client.read(len(expected[1])), expected[1])
            # This reply is a barrier: accepted pong/control cannot be mistaken for silence.
            client.send(b'after-policy')
            expect(client.receive(), b'after-policy')
            client.send(b'\x03\xe8', opcode=8)
            expect(client.read(4), b'\x88\x02\x03\xe8')
            expect(client.socket.recv(1), b'')
            row['observed'] = 'reply-barrier-and-close-eof'
        row['passed'] = True
    except Exception as error:
        row['error'] = f'{type(error).__name__}: {error}'
    finally:
        client.close()
    try:
        status, _, body = request(port)
        expect(status, 200)
        expect(body, b'healthy')
        row['health_after'] = True
    except Exception as error:
        row['passed'] = False
        row['health_error'] = f'{type(error).__name__}: {error}'
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-invalid.json'))
    args = parser.parse_args()
    entry = Path(__file__).with_suffix('.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': PIN,
              'scope': 'Explicit pinned policy, not RFC conformance. Each case uses a fresh socket; rejected connections must terminate (EOF/reset), timeout fails. Accepted controls have a text reply barrier. HTTP health checked after every case. Configured and effective aggregate payload limit65536 (native minimum); each fragment wire length below65536. This supplements original PHPTs without replacing their outcomes.',
              'engines': [], 'results': []}
    for engine in parse_engines(args.engine, args.php, args.php_extension):
        report['engines'].append(engine.metadata())
        row = {'engine': engine.name, 'cases': [], 'passed': False}
        try:
            with server(engine, entry) as (port, _):
                row['cases'] = [run_case(port, *case) for case in scenarios()]
            expect(len(row['cases']), 20)
            row['passed'] = all(case['passed'] for case in row['cases'])
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        report['results'].append(row)
    write_report(args.output, report)
    print(json.dumps(report['results']))
    return int(any(not row['passed'] for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
