#!/usr/bin/env python3
"""Instructions per request for a benchmark workload, counted by callgrind.

Instruction counts barely vary between runs of the same binary, so hybrid/upstream
ratios are stable on shared CI runners where timings are not. Only requests are
counted: instrumentation is switched on after startup and warmup, and off before
shutdown. Every process (master, manager, worker) is followed and summed.
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
    parser.add_argument('--workload', choices=list(WORKLOADS), default='plaintext')
    parser.add_argument('--requests', type=int, default=2000)
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profiles', type=Path, help='Keep the callgrind profiles in DIR/<engine>/')
    args = parser.parse_args()
    results = {}
    for engine in parse_engines(args.engine, args.php, args.php_extension):
        results[engine.name] = instructions(engine, WORKLOADS[args.workload], args.requests, args.warmup, args.profiles)
        print(f'{engine.name:10} {args.workload:15} {results[engine.name]:12.0f} instructions/request', flush=True)
    if len(results) == 2:
        first, second = results.values()
        print(f'ratio {list(results)[0]}/{list(results)[1]}: {first / second:.4f}')
    if args.output:
        args.output.write_text(json.dumps({'workload': args.workload, 'requests': args.requests,
                                           'instructions_per_request': results}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
