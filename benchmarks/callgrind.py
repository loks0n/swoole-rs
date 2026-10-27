#!/usr/bin/env python3
"""Instructions per request for benchmark workloads, counted by callgrind.

Instruction counts barely vary between runs of the same binary, so hybrid/upstream
ratios are stable on shared CI runners where timings are not. Only requests are
counted: instrumentation is switched on after startup and warmup, and off before
shutdown. Every process (master, manager, worker) is followed and summed.
With two engines and --max-ratio, exits 1 if any workload's first/second ratio exceeds it.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run import WORKLOADS
from tools.harness import ROOT, parse_engines


def wait_for_port(port, proc, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'server exited during startup ({proc.returncode})')
        try:
            socket.create_connection(('127.0.0.1', port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError('server did not listen in time')


def send(port, workload, count):
    _, method, path, payload, expected = workload
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    for _ in range(count):
        conn.request(method, path, payload)
        response = conn.getresponse()
        body = response.read()
        if response.status != 200 or body != expected:
            raise RuntimeError(f'unexpected response {response.status}: {body[:80]!r}')
    conn.close()


def instructions(engine, workload, requests, warmup, profiles=None):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='swr-callgrind-') as out, tempfile.TemporaryDirectory() as data:
        command = ['valgrind', '--tool=callgrind', '--trace-children=yes', '--instr-atstart=no',
                   f'--callgrind-out-file={out}/cg.%p',
                   *engine.command(ROOT / 'corpus' / workload[0] / 'server.php')]
        proc = subprocess.Popen(command, env={**os.environ, 'TEST_PORT': str(port), 'TEST_DATA': data},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            wait_for_port(port, proc)
            send(port, workload, warmup)
            subprocess.run(['callgrind_control', '-i', 'on'], check=True, capture_output=True)
            send(port, workload, requests)
            subprocess.run(['callgrind_control', '-i', 'off'], check=True, capture_output=True)
            # Dump now: a signalled valgrind may exit without writing its profile.
            subprocess.run(['callgrind_control', '-d'], check=True, capture_output=True)
        finally:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=120)
        total = 0
        if profiles:
            shutil.copytree(out, profiles / engine.name, dirs_exist_ok=True)
        for path in Path(out).glob('cg.*'):
            for line in path.read_text(errors='replace').splitlines():
                if line.startswith('totals:'):
                    total += int(line.split()[1])
        return total / requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True, help='NAME=/path/to/extension')
    parser.add_argument('--workload', choices=list(WORKLOADS), action='append')
    parser.add_argument('--requests', type=int, default=2000)
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    # Large output stays in this worktree's target/, where dev.py prune finds it (#395, #396).
    run = ROOT / 'target' / 'callgrind' / time.strftime('%Y%m%dT%H%M%S')
    parser.add_argument('--output', type=Path, default=run / 'callgrind.json')
    parser.add_argument('--profiles', type=Path, nargs='?', const=run / 'profiles',
                        help='Keep the callgrind profiles in DIR/<workload>/<engine>/ (default under target/callgrind/)')
    parser.add_argument('--max-ratio', type=float, help='Fail if first/second exceeds this for any workload')
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if args.max_ratio and len(engines) != 2:
        parser.error('--max-ratio needs exactly two engines')
    results, failed = {}, False
    for workload in args.workload or ['plaintext']:
        counts = results[workload] = {}
        profiles = args.profiles / workload if args.profiles else None
        for engine in engines:
            counts[engine.name] = instructions(engine, WORKLOADS[workload], args.requests, args.warmup, profiles)
            print(f'{engine.name:10} {workload:15} {counts[engine.name]:12.0f} instructions/request', flush=True)
        if len(counts) == 2:
            (first, a), (second, b) = counts.items()
            over = args.max_ratio and a / b > args.max_ratio
            failed |= bool(over)
            print(f'ratio {first}/{second} {workload}: {a / b:.4f}' + (f' exceeds {args.max_ratio}' if over else ''))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'requests': args.requests, 'max_ratio': args.max_ratio,
                                       'instructions_per_request': results}, indent=2) + '\n')
    print('results: ' + str(args.output))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
