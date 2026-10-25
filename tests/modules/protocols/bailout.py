#!/usr/bin/env python3
"""Real request-side Zend throws, exits and parameter-allocation exhaustion."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, server, write_report

PAYLOAD = 3 * 1024 * 1024
HEALTH = b'*1\r\n$4\r\nECHO\r\n'


def probe(engine, mode, coroutines, scenario):
    command = scenario.upper().encode()
    wire = b'*1\r\n$' + str(len(command)).encode() + b'\r\n' + command + b'\r\n'
    if scenario == 'oom':
        wire = b'*2' + wire[2:] + b'$' + str(PAYLOAD).encode() + b'\r\n' + b'x' * PAYLOAD + b'\r\n'
    row = {'mode': mode, 'coroutines': coroutines, 'scenario': scenario,
           'wire_bytes': len(wire), 'wire_sha256': hashlib.sha256(wire).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='swr-request-bailout-') as directory:
        root = Path(directory)
        log, events = root / 'errors.log', root / 'events.jsonl'
        env = {'TEST_SERVER_MODE': mode, 'TEST_COROUTINES': str(int(coroutines)),
               'TEST_SCENARIO': scenario, 'TEST_LOG_FILE': str(log), 'TEST_EVENTS': str(events)}
        with server(engine, Path(__file__).with_suffix('.php'), env) as (port, proc):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=3) as peer:
                    peer.settimeout(.5)
                    peer.sendall(wire)
                    received = peer.recv(32)
                    row['termination'] = 'eof' if not received else 'response:' + received.hex()
            except (ConnectionResetError, BrokenPipeError):
                row['termination'] = 'reset'
            except socket.timeout:
                row['termination'] = 'timeout'
            healthy = False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and proc.poll() is None:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2) as peer:
                        peer.settimeout(.2)
                        peer.sendall(HEALTH)
                        healthy = peer.recv(32) == b'+OK\r\n'
                    if healthy:
                        break
                except OSError:
                    pass
                time.sleep(.02)
            row['master_exit'] = proc.poll()
            row['healthy'] = healthy
            row['events'] = [json.loads(line) for line in events.read_text().splitlines()]
        row['log'] = log.read_text() if log.exists() else ''
    errors = [event[1:] for event in row['events'] if event[0] == 'worker-error']
    entered = [event[1:] for event in row['events'] if event[0] == 'entered']
    row['witness'] = {'healthy': healthy, 'master_exit': row['master_exit'], 'worker_errors': errors,
                      'entered': entered, 'connection': 'closed' if row['termination'] in ['eof', 'reset'] else row['termination']}
    try:
        assert row['events'][0][0] == 'start', 'Missing worker-ready checkpoint'
        assert 'panicked at' not in row['log'], 'Unexpected Rust panic'
        if scenario == 'oom':
            allocations = re.findall(r'Allowed memory size of (\d+) bytes exhausted \(tried to allocate (\d+) bytes\)', row['log'])
            assert allocations and not entered, 'Expected native allocation exhaustion before callback'
            # PHP8.5/macOS reports payload+32; PHP8.2/Linux reports the next
            # 4KiB page. Both exclude the earlier 4MiB receive-buffer failure.
            attempts = {int(attempt) for _, attempt in allocations}
            assert len(attempts) == 1 and attempts <= {PAYLOAD + 32, PAYLOAD + 4096}, allocations
            row['witness']['oom'] = {'attempted_bytes': attempts.pop()}
            assert row['master_exit'] == 255 or [255, 0] in errors, 'Expected PHP fatal status, never a signal abort'
        else:
            assert entered == [[scenario]], 'Callback did not enter'
            assert healthy or row['master_exit'] == 255 or [255, 0] in errors, 'Expected recovery or original PHP fatal outcome'
            expected = 'RuntimeException: request-boundary-exception' if scenario == 'throw' else 'Swoole\\ExitException: swoole exit'
            assert expected in row['log'], 'Missing native callback exception diagnostic'
            row['witness']['exception'] = expected
    except AssertionError as error:
        row['validation_error'] = str(error)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/protocols-bailout.json')
    args = parser.parse_args()
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'engines': [], 'results': [],
              'scope': 'Real native PHP request-side exceptional outcomes; expected OOM fatalities recorded separately from successful requests. EOF/reset transport races retained raw but classified as closed for differential comparison.'}
    reference = {}
    for engine_index, engine in enumerate(parse_engines(args.engine, args.php)):
        report['engines'].append(engine.metadata())
        for mode in ['base', 'process']:
            for scenario, coroutines in [('throw', False), ('throw', True), ('exit', False), ('exit', True), ('oom', False)]:
                key = (mode, scenario, coroutines)
                row = {'engine': engine.name, 'mode': mode, 'scenario': scenario, 'coroutines': coroutines, 'matched': False}
                try:
                    row.update(probe(engine, mode, coroutines, scenario))
                    assert not row.get('validation_error'), row.get('validation_error')
                    if engine_index == 0:
                        reference[key] = row['witness']
                    assert key in reference, 'Reference scenario did not validate'
                    assert row['witness'] == reference[key], 'Native lifecycle outcome differs from reference'
                    row['matched'] = True
                except (AssertionError, OSError, RuntimeError, ValueError) as error:
                    row['error'] = f'{type(error).__name__}: {error}'
                report['results'].append(row)
                write_report(args.output, report)
    print(json.dumps({'matched': sum(row['matched'] for row in report['results']), 'scenarios': len(report['results'])}))
    return int(any(not row['matched'] for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
