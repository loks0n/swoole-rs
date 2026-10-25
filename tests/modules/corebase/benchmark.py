#!/usr/bin/env python3
"""Measure prepared public-call batches only during an explicitly granted host-wide lease."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import uuid
from prepare_benchmark import EXPECTED, ROOT, clean_environment, sha
from tools.harness import run_isolated
from tools.native_core import library_identity

# Fixed, uncalibrated counts; change the recorded profile under the measurement
# lease if necessary, never infer a clean measurement window from this script.
COUNTS = {name: (10000 if name == 'mkdir_existing' else
                 200000 if name in ('radix_alloc_release', 'dirname') else 1000000)
          for name in EXPECTED}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measure', action='store_true', help='Execution mode, NOT lease authorization')
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--counts', type=Path, help='Recorded per-workload count profile, including any calibration under the lease')
    parser.add_argument('--repetitions', type=int, default=7)
    args = parser.parse_args()
    if not args.measure or args.repetitions < 3:
        parser.error('Explicit --measure and at least three repetitions required; caller must hold the actual lease')
    counts = json.loads(args.counts.read_text()) if args.counts else COUNTS.copy()
    if set(counts) != set(EXPECTED) or any(type(v) is not int or not 0 < v < (1 << 64) for v in counts.values()):
        parser.error('Count profile must name every workload with a positive uint64 count')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    attempt = args.output.parent.resolve() / ('corebase-timings-' + uuid.uuid4().hex); attempt.mkdir()
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), passed=False,
                  scope='Exact ordinary public-facade workloads including call/reduction overhead, no baseline subtraction. Not whole-project/PHP/default-activation proof. Caller supplies actual exclusive lease; execution flag grants none.',
                  activation_ready=False, prepared=str(args.prepared.resolve()),
                  counts=counts, repetitions=args.repetitions, warmup_iterations=1, results=[], summaries={}, attempt=str(attempt))

    def checkpoint():
        body = json.dumps(report, indent=2) + '\n'
        temporary = attempt / 'report.next.json'; temporary.write_text(body); temporary.replace(attempt / 'report.json')
        index = attempt / 'index.next.json'; index.write_text(body); index.replace(args.output)

    try:
        prepared = json.loads(args.prepared.read_text())
        if not prepared['passed'] or prepared['expected_per_iteration'] != EXPECTED:
            raise ValueError('Preparation/checksum profile is stale or failed')
        executable = Path(prepared['engines']['native']['measure_command_template'][0])
        env, report['removed_tracing'] = clean_environment()
        report['matched_environment'] = {k: env.get(k, '') for k in ('LANG', 'LC_ALL', 'LC_CTYPE', 'LC_NUMERIC', 'MALLOC_CONF', 'MALLOC_ARENA_MAX', 'GLIBC_TUNABLES', 'LD_BIND_NOW', 'DYLD_BIND_AT_LAUNCH', 'MallocNanoZone', 'MallocStackLogging')}

        def verify():
            if sha(executable) != prepared['executable_sha256']: raise ValueError('Prepared executable changed')
            for row in prepared['engines'].values():
                if library_identity(row['library']['path']) != row['library']: raise ValueError('Prepared library changed')

        names = list(EXPECTED)
        for repeat in range(args.repetitions):
            order = names[repeat % len(names):] + names[:repeat % len(names)]
            for name in order:
                for engine in (['native', 'rust'] if repeat % 2 == 0 else ['rust', 'native']):
                    row = prepared['engines'][engine]; count = counts[name]; verify()
                    command = [str(count) if x == 'ITERATIONS' else x for x in row['measure_workloads'][name]]
                    if command[0] != str(executable) or command[1] != '--measure' or command[-1] != name:
                        raise ValueError('Foreign measurement command')
                    chosen = {**env, **row['measure_environment']}
                    log = attempt / (str(len(report['results'])) + '.log')
                    trial = dict(repeat=repeat, engine=engine, workload=name, iterations=count,
                                 command=command, environment=row['measure_environment'],
                                 log=str(log), passed=False, state='started')
                    report['results'].append(trial); checkpoint()
                    try:
                        result = run_isolated(command, cwd=ROOT, timeout=30, env=chosen)
                    except subprocess.TimeoutExpired as error:
                        def decoded(value):
                            return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
                        log.write_text(decoded(error.stdout) + decoded(error.stderr))
                        trial.update(state='timed_out', timeout_seconds=30, error=str(error),
                                     cleanup='Shared run_isolated attempts process-group termination before propagating; no independent PID observation')
                        checkpoint(); verify()
                        raise
                    log.write_text(result.stdout + result.stderr)
                    trial.update(state='exited', exit=result.returncode)
                    checkpoint(); verify()
                    if result.returncode or result.stderr: raise ValueError('Measured process failed; raw failure retained')
                    rows = [json.loads(line) for line in result.stdout.splitlines()]
                    if len(rows) != 1: raise ValueError('Missing/duplicate measured workload')
                    measured = rows[0]
                    if (measured['workload'] != name or measured['iterations'] != count
                            or measured['checksum'] != (EXPECTED[name] * count) % (1 << 64)
                            or type(measured['elapsed_ns']) is not int or measured['elapsed_ns'] <= 0):
                        raise ValueError('Measured checksum/count/clock mismatch')
                    trial.update(passed=True, **measured); checkpoint()
        for name in names:
            medians = {engine: statistics.median(r['elapsed_ns'] for r in report['results']
                       if r['workload'] == name and r['engine'] == engine) for engine in ['native', 'rust']}
            report['summaries'][name] = dict(native_ns_median=medians['native'], rust_ns_median=medians['rust'],
                native_over_rust=medians['native'] / medians['rust'],
                calls_per_iteration=prepared['engines']['native']['calls_per_iteration'][name])
        report['correctness_passed'] = True
        report['observed_slower_medians'] = [n for n, s in report['summaries'].items() if s['native_over_rust'] < 1]
        report['passed'] = not report['observed_slower_medians']
    except Exception as error:
        report['error'] = str(error)
    checkpoint()
    print(json.dumps({k: report.get(k) for k in ['passed', 'observed_slower_medians', 'error']}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
