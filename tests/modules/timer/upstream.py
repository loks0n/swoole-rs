#!/usr/bin/env python3
"""Whole pinned timer PHPT inventory; original assertions and official runner."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import ROOT, parse_engines

EXTERNAL = {'bug_4794_3', 'bug_4794_5', 'bug_4794_6', 'bug_4794_7'}


def selection(source, external=False, names=()):
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if pin != COMMIT:
        raise ValueError('Timer source HEAD differs from frozen pin')
    paths = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only', COMMIT,
                                    'tests/swoole_timer'], text=True).splitlines()
    paths = sorted(path for path in paths if path.endswith('.phpt'))
    if len(paths) != 33 or not EXTERNAL <= {Path(path).stem for path in paths}:
        raise ValueError('Pinned 33-case timer inventory differs; review selection')
    if set(names) - {Path(path).stem for path in paths}:
        raise ValueError('Unknown timer --case name')
    selected, unmeasured = [], []
    for path in paths:
        name = Path(path).stem
        if names and name not in names or name in EXTERNAL and not external:
            unmeasured.append(path)
            continue
        original = subprocess.check_output(['git', '-C', str(source), 'show', f'{COMMIT}:{path}'])
        selected.append({'path': path, 'module': 'timers', 'sha256': hashlib.sha256(original).hexdigest()})
    if not selected:
        raise ValueError('No timer cases selected; external cases require --external-network')
    return selected, unmeasured


def require_free_port(port=9601):
    # Match reusable listeners without rejecting a prior engine's closed socket
    # still in TCP TIME_WAIT. A live listener on this address remains an error.
    with socket.socket() as guard:
        guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        guard.bind(('127.0.0.1', port))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--external-network', action='store_true', help='Explicitly include four route/DNS-dependent cases')
    parser.add_argument('--case', action='append', default=[], help='Exact original timer basename without .phpt')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/timer-upstream.json')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': COMMIT,
              'scope': 'Original pinned timer PHPTs, serial isolated official runner; no assertion or expected-output changes.',
              'inventory_count': 33, 'engines': [], 'results': [], 'batches': [],
              'passed': False, 'execution_status': 'running'}
    try:
        cases, unmeasured = selection(args.source, args.external_network, args.case)
        report.update(selected_cases=[case['path'] for case in cases], unmeasured_cases=unmeasured)
        save_report(args.output, report)
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            report['engines'].append(engine.metadata())
            # Each engine gets fresh disposable support files, including result.txt.
            with tempfile.TemporaryDirectory(prefix='swr-timer-original-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                for case in cases:
                    artifact = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name / Path(case['path']).stem
                    if Path(case['path']).stem == 'bug_4794_8':
                        try:
                            require_free_port()
                        except OSError as error:
                            record_result(report, engine, case, {'status': 'failed', 'detail': f'Fixed port 9601 unavailable: {error}'})
                            save_report(args.output, report)
                            continue
                    results, timing = run_cases(engine, [case], sandbox, artifact, args.timeout, 1, offline=not args.external_network)
                    report['batches'].append({'engine': engine.name, **timing})
                    record_result(report, engine, case, results[case['path']])
                    save_report(args.output, report)
        report['execution_status'] = 'complete'
        report['passed'] = bool(report['results']) and all(row['status'] == 'passed' for row in report['results'])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['execution_status'] = 'failed'
        print(report['error'], file=sys.stderr)
    finally:
        if report['execution_status'] == 'running':
            report['execution_status'] = 'interrupted'
        save_report(args.output, report)
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
