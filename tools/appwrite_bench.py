#!/usr/bin/env python3
"""Appwrite endpoint load, stock (upstream) against hybrid Swoole.

  appwrite_bench.py run VARIANT TRIAL OUT   load the running stack once, write OUT/VARIANT-TRIAL.json
  appwrite_bench.py report OUT              Markdown medians across trials, per endpoint and variant

`run` drives each endpoint with ApacheBench (keep-alive, fixed request count and
concurrency) from the host and samples the appwrite container's memory with
`docker stats` after the load. appwrite-e2e.yml alternates the variants on one
runner so both see the same machine.
"""
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

URL = 'http://localhost/v1'
REQUESTS, CONCURRENCY = 5000, 32
# Public health, and a project-scoped read that goes through Appwrite's router and auth.
ENDPOINTS = {
    'health-version': ('/health/version', []),
    'locale-countries': ('/locale/countries', ['-H', 'X-Appwrite-Project: console']),
}


def ab(path, headers):
    command = ['ab', '-q', '-k', '-n', str(REQUESTS), '-c', str(CONCURRENCY), *headers, URL + path]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    number = lambda pattern: float(re.search(pattern, output, re.M).group(1))
    return {'requests_per_second': number(r'^Requests per second:\s+([\d.]+)'),
            'p50_ms': number(r'^\s+50%\s+(\d+)'), 'p99_ms': number(r'^\s+99%\s+(\d+)'),
            'failed': int(number(r'^Failed requests:\s+(\d+)')),
            'non_2xx': int(number(r'^Non-2xx responses:\s+(\d+)')) if 'Non-2xx' in output else 0}


def memory_mib():
    usage = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}', 'appwrite'],
                           capture_output=True, text=True, check=True).stdout.split('/')[0].strip()
    value, unit = re.match(r'([\d.]+)\s*([KMG]i?B)', usage).groups()
    return float(value) * {'KiB': 1 / 1024, 'MiB': 1, 'GiB': 1024, 'KB': 1 / 1000, 'MB': 1, 'GB': 1000}[unit]


def run(variant, trial, out):
    results = {name: ab(path, headers) for name, (path, headers) in ENDPOINTS.items()}
    record = {'variant': variant, 'trial': int(trial), 'requests': REQUESTS, 'concurrency': CONCURRENCY,
              'endpoints': results, 'appwrite_memory_mib': memory_mib()}
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{variant}-{trial}.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


def report(out):
    records = [json.loads(path.read_text()) for path in sorted(out.glob('*.json'))]
    variants = sorted({record['variant'] for record in records})
    median = lambda variant, pick: statistics.median(pick(r) for r in records if r['variant'] == variant)
    lines = [f'**Appwrite endpoint load** ({REQUESTS} requests, concurrency {CONCURRENCY}, median of '
             f'{len(records) // max(len(variants), 1)} alternating trials)', '',
             '| endpoint | metric | ' + ' | '.join(variants) + ' |', '| --- | --- |' + ' --- |' * len(variants)]
    for name in ENDPOINTS:
        for metric in ['requests_per_second', 'p50_ms', 'p99_ms', 'failed', 'non_2xx']:
            values = [f"{median(v, lambda r: r['endpoints'][name][metric]):.1f}" for v in variants]
            lines.append(f'| {name} | {metric} | ' + ' | '.join(values) + ' |')
    values = [f"{median(v, lambda r: r['appwrite_memory_mib']):.0f}" for v in variants]
    lines.append('| appwrite container | memory MiB | ' + ' | '.join(values) + ' |')
    print('\n'.join(lines))
    return int(any(r['endpoints'][name]['failed'] or r['endpoints'][name]['non_2xx']
                   for r in records for name in ENDPOINTS))


if __name__ == '__main__':
    if sys.argv[1:2] == ['run'] and len(sys.argv) == 5:
        run(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    elif sys.argv[1:2] == ['report'] and len(sys.argv) == 3:
        sys.exit(report(Path(sys.argv[2])))
    else:
        sys.exit(__doc__)
