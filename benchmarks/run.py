#!/usr/bin/env python3
"""Small closed-loop HTTP benchmarks, using the same corpus and engine harness."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import http.client
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT, parse_engines, server, write_report

PAYLOAD = bytes(range(256)) * 256
WORKLOADS = {
    'plaintext': ('01-hello', 'GET', '/', None, b'Hello, Swoole!\n'),
    'json': ('02-router', 'GET', '/inspect?q=benchmark', None,
             b'{"query":{"q":"benchmark"},"token":null}'),
    'echo-64k': ('02-router', 'POST', '/echo', PAYLOAD, PAYLOAD),
    'service-health': ('04-job-service', 'GET', '/health', None, b'{"ok":true}'),
}


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def measure(port, workload, requests, concurrency, warmup):
    _, method, path, payload, expected = workload
    clock = {}
    barrier = threading.Barrier(concurrency + 1, action=lambda: clock.update(start=time.perf_counter()), timeout=15)

    def exchange(conn):
        conn.request(method, path, payload)
        response = conn.getresponse()
        body = response.read()
        if response.status != 200 or body != expected:
            raise AssertionError(f'HTTP {response.status}, incorrect body={body[:80]!r}')
        if conn.sock is None:
            raise AssertionError('keep-alive connection closed')
        return len(body)

    def worker(index):
        latencies, errors, transferred = [], [], 0
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        count = requests // concurrency + (index < requests % concurrency)
        try:
            # Establish all connections and warm each one before the timed barrier.
            for _ in range(warmup):
                exchange(conn)
            barrier.wait()
            for _ in range(count):
                started = time.perf_counter_ns()
                try:
                    transferred += exchange(conn)
                    latencies.append((time.perf_counter_ns() - started) / 1_000_000)
                except Exception as error:
                    errors.append(str(error))
                    conn.close()
        except BaseException:
            barrier.abort()
            raise
        finally:
            conn.close()
        return latencies, errors, transferred

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, i) for i in range(concurrency)]
        # Timestamp in the barrier action, before any load worker is released.
        barrier.wait()
        results = [future.result() for future in futures]
        elapsed = time.perf_counter() - clock['start']
    latencies = [latency for values, _, _ in results for latency in values]
    errors = [error for _, values, _ in results for error in values]
    return {'requests': requests, 'successes': len(latencies), 'errors': len(errors),
            'error_examples': errors[:5], 'seconds': elapsed,
            'requests_per_second': len(latencies) / elapsed,
            'body_bytes': sum(size for _, _, size in results),
            'latency_ms': {'p50': percentile(latencies, .5), 'p95': percentile(latencies, .95),
                           'p99': percentile(latencies, .99), 'max': max(latencies, default=None)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True, help='NAME=/path/to/extension; repeat to compare')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[], help='Extra PHP module to load before Swoole; repeat as needed')
    parser.add_argument('--workload', choices=list(WORKLOADS), action='append')
    parser.add_argument('--requests', type=int, default=2000, help='Measured requests per trial')
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1, 16])
    parser.add_argument('--warmup', type=int, default=20, help='Requests per connection before measurement')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--output', default=str(ROOT / 'target/reports/benchmarks.json'))
    args = parser.parse_args()
    if args.requests <= 0 or args.repeat <= 0 or args.warmup <= 0 or any(c <= 0 or c > args.requests for c in args.concurrency):
        parser.error('Counts must be positive and concurrency must not exceed requests')
    engines = parse_engines(args.engine, args.php, args.php_extension)
    metadata = [engine.metadata() for engine in engines]
    for engine in metadata:
        required = {'http'} | ({'sqlite'} if not args.workload or 'service-health' in args.workload else set())
        if not required <= set(engine['capabilities']):
            parser.error(f'{engine["name"]} lacks benchmark capabilities: {required - set(engine["capabilities"])}')
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True)
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'host': {'platform': platform.platform(), 'machine': platform.machine(), 'cpus': os.cpu_count(),
                       'python': platform.python_version()},
              'revision': revision.stdout.strip() if revision.returncode == 0 else None,
              'dirty': bool(dirty.stdout.strip()), 'engines': metadata,
              'parameters': {'requests': args.requests, 'concurrency': args.concurrency,
                             'warmup_per_connection': args.warmup, 'repeat': args.repeat,
                             'load_model': 'closed-loop; one outstanding request per persistent connection'},
              'results': [], 'summary': []}
    for name in args.workload or WORKLOADS:
        workload = WORKLOADS[name]
        for concurrency in args.concurrency:
            for trial in range(args.repeat):
                # Alternate engine order between trials to reduce ordering bias.
                for engine in engines[::1 if trial % 2 == 0 else -1]:
                    entry = ROOT / 'corpus' / workload[0] / 'server.php'
                    with server(engine, entry) as (port, _):
                        result = measure(port, workload, args.requests, concurrency, args.warmup)
                    row = {'engine': engine.name, 'workload': name, 'concurrency': concurrency,
                           'trial': trial + 1, **result}
                    report['results'].append(row)
                    print(f'{engine.name:10} {name:15} c={concurrency:<3} trial={trial+1} '
                          f'{result["requests_per_second"]:9.0f} req/s '
                          f'p99={result["latency_ms"]["p99"]}ms errors={result["errors"]}', flush=True)
                    # Retain completed trials if a later trial fails or is interrupted.
                    write_report(args.output, report)
            for engine in engines:
                rows = [r for r in report['results'] if r['engine'] == engine.name and r['workload'] == name and r['concurrency'] == concurrency]
                valid = [r for r in rows if r['errors'] == 0]
                report['summary'].append({'engine': engine.name, 'workload': name, 'concurrency': concurrency,
                                          'valid_trials': len(valid), 'total_trials': len(rows),
                                          'median_requests_per_second': statistics.median(r['requests_per_second'] for r in valid) if valid else None})
    write_report(args.output, report)
    print(f'Report: {args.output}')
    return int(any(row['errors'] for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
