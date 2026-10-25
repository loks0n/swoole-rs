#!/usr/bin/env python3
"""Independent response-barrier diagnostic; never substitutes for original PHPT."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.run import WebSocket, expect
from tools.harness import ROOT, parse_engines, request, server, write_report


def frame(payload, opcode=1, final=True):
    mask = b'\x00\x01\x80\xff'
    length = len(payload)
    header = bytes([(0x80 if final else 0) | opcode])
    header += (bytes([0x80 | length]) if length < 126 else
               b'\xfe' + struct.pack('!H', length) if length <= 65535 else
               b'\xff' + struct.pack('!Q', length))
    return header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload))


def transport_matrix(port):
    client = WebSocket(port)
    cases = []
    try:
        client.socket.sendall(frame(b'first') + frame(b'second'))
        expect(client.receive(), b'first')
        expect(client.receive(), b'second')
        cases.append('coalesced-text')
        for length in [125, 126, 65535, 65536]:
            payload = b'x' * length
            wire = frame(payload)
            cuts = sorted(set([0, 1, 2, 3, 4, 7, 11, len(wire)] + list(range(4096, len(wire), 4096))))
            for start, end in zip(cuts, cuts[1:]):
                client.socket.sendall(wire[start:end])
            expect(client.receive(), payload)
            cases.append('split-writes-' + str(length))
        client.socket.sendall(frame(b'fragment-', final=False) + frame(b'P', opcode=9) +
                              frame(b'complete', opcode=0))
        expect(client.read(2), b'\x8a\x01')
        expect(client.read(1), b'P')
        expect(client.receive(), b'fragment-complete')
        cases.append('fragment-ping-continuation')
        client.send(b'\x03\xe8', opcode=8)
        expect(client.read(2), b'\x88\x02')
        expect(client.read(2), b'\x03\xe8')
        expect(client.socket.recv(1), b'')
        cases.append('close-eof')
    finally:
        client.close()
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-close-probe.json'))
    args = parser.parse_args()
    entry = Path(__file__).with_suffix('.php')
    engines = parse_engines(args.engine, args.php)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Seven raw transport cases (write splitting does not guarantee receive splitting) plus independent response-barrier diagnostic. Two messages precede reading close and text replies. Client remains alive until replies; original send_close_frame PHPT remains unchanged and failed. This does not prove its failure cause.',
              'engines': [engine.metadata() for engine in engines], 'results': []}
    for engine in engines:
        row = {'engine': engine.name, 'passed': False}
        try:
            with server(engine, entry) as (port, _):
                row['transport_cases'] = transport_matrix(port)
                client = WebSocket(port)
                try:
                    client.send(b'aaa')
                    client.send(b'lalalala')
                    expect(client.read(2), b'\x88\x0c')
                    expect(client.read(12), b'\x03\xe8diagnostic')
                    expect(client.receive(), b'lalalala')
                    status, _, body = request(port)
                    expect(status, 200)
                    expect(body, b'healthy')
                    row['passed'] = True
                finally:
                    client.close()
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
        report['results'].append(row)
    write_report(args.output, report)
    print(json.dumps(report['results']))
    return int(any(not row['passed'] for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
