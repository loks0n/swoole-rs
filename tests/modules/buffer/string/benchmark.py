#!/usr/bin/env python3
"""Time already-built, provenance-checked String consumers on an idle host."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tools.harness import run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-report', type=Path, required=True)
    parser.add_argument('--previous-prepared-report', type=Path, help='Matched previous Rust consumer compiled from the same benchmark source')
    parser.add_argument('--workloads', nargs='+', default=['append-4k', 'append-cold', 'repeat-4k', 'write-reduce', 'query-4k', 'split-4k', 'split-missing'], help='Prepared workload subset for a short combined timing window')
    parser.add_argument('--repeat', type=int, default=9)
    parser.add_argument('--iterations', type=int, default=100000)
    parser.add_argument('--output', default='target/reports/string-benchmark.json')
    args = parser.parse_args()
    if args.repeat < 1 or args.iterations < 1: parser.error('Repeat and iterations must be positive')
    prepared = json.loads(args.prepared_report.read_text())
    if not prepared.get('prepared') or prepared.get('sanitize_cpp_only'): parser.error('Need optimized prepared consumers')
    artifacts = dict(prepared['engines'])
    previous = json.loads(args.previous_prepared_report.read_text()) if args.previous_prepared_report else None
    if previous:
        if not previous.get('prepared') or previous.get('sanitize_cpp_only'): parser.error('Previous consumers must be optimized')
        if previous['adapter_sha256']['benchmark.cc'] != prepared['adapter_sha256']['benchmark.cc']: parser.error('Benchmark source differs')
        artifacts['previous'] = previous['engines']['rust']
    for row in artifacts.values():
        if hashlib.sha256(Path(row['binary']).read_bytes()).hexdigest() != row['binary_sha256']: parser.error('Consumer binary changed')
    report = {'scope': 'Optimized native String consumer, not PHP throughput. No sanitizers. Existing allocator and retained native dependencies identical. Payload/accounting pre/postflight; timed checksum; rotated/reversed engine order.',
              'prepared': prepared, 'previous_prepared': previous, 'trials': [], 'comparisons': []}
    for workload in args.workloads:
        names = list(artifacts)
        rows = {name: [] for name in names}
        for trial in range(args.repeat):
            order = names[trial % len(names):] + names[:trial % len(names)]
            if trial % 2: order.reverse()
            for engine in order:
                result = run_isolated([artifacts[engine]['binary'], workload, str(args.iterations)], timeout=30)
                row = {'workload': workload, 'engine': engine, 'trial': trial, 'returncode': result.returncode, 'stderr': result.stderr}
                report['trials'].append(row)
                if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
                row.update(json.loads(result.stdout)); rows[engine].append(row['ns_per_cycle'])
                if row['errors']: write_report(args.output, report); return 1
        before, after = [statistics.median(rows[name]) for name in ['upstream', 'rust']]
        comparison = {'workload': workload, 'upstream_ns': before, 'rust_ns': after, 'throughput_ratio': before / after}
        if previous:
            old = statistics.median(rows['previous'])
            comparison.update(previous_rust_ns=old, previous_to_current=old / after)
        report['comparisons'].append(comparison)
    report['errors'] = sum(row['errors'] for row in report['trials'])
    write_report(args.output, report)
    print(json.dumps(report['comparisons']))
    return 0
if __name__ == '__main__': sys.exit(main())
