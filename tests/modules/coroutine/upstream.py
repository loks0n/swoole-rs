#!/usr/bin/env python3
"""Whole pinned coroutine/channel/scheduler PHPT inventory; original assertions and official runner."""
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

GROUPS = {'swoole_coroutine': 145, 'swoole_channel_coro': 44, 'swoole_coroutine_scheduler': 28}


def selection(source, groups=(), names=()):
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if pin != COMMIT:
        raise ValueError('Coroutine source HEAD differs from frozen pin')
    inventory = []
    for group, count in GROUPS.items():
        paths = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only', COMMIT,
                                        'tests/' + group], text=True).splitlines()
        paths = sorted(path for path in paths if path.endswith('.phpt'))
        if len(paths) != count:
            raise ValueError('Pinned coroutine original inventory differs: ' + group)
        for path in paths:
            original = subprocess.check_output(['git', '-C', str(source), 'show', f'{COMMIT}:{path}'])
            inventory.append({'path': path, 'module': 'coroutine', 'group': group,
                              'sha256': hashlib.sha256(original).hexdigest()})
    if set(names) - {case['path'] for case in inventory}:
        raise ValueError('Unknown exact original --case path')
    selected = [case for case in inventory if (not groups or case['group'] in groups) and (not names or case['path'] in names)]
    if not selected:
        raise ValueError('No coroutine cases selected')
    return inventory, selected


def require_free_case_port(case):
    if case['path'] == 'tests/swoole_coroutine/cancel/socket.phpt':
        # Original is UDP9601, independent of the timer original TCP9601.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as guard:
            guard.bind(('127.0.0.1', 9601))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--external-network', action='store_true', help='Explicitly include four route/DNS-dependent cases')
    parser.add_argument('--case', action='append', default=[], help='Exact pinned tests/... relative path; default selects all201')
    parser.add_argument('--group', action='append', choices=sorted(GROUPS), default=[])
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/coroutine-upstream.json')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': COMMIT,
              'scope': 'Original pinned coroutine/channel/scheduler PHPTs, serial isolated official runner; no assertion or expected-output changes.',
              'inventory_count': 201, 'engines': [], 'results': [], 'batches': [],
              'passed': False, 'execution_status': 'running'}
    try:
        inventory, cases = selection(args.source, args.group, args.case)
        unmeasured = [case['path'] for case in inventory if case not in cases]
        report['inventory'] = inventory
        report.update(selected_cases=[case['path'] for case in cases], unmeasured_cases=unmeasured)
        save_report(args.output, report)
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            report['engines'].append(engine.metadata())
            # Each engine gets fresh disposable support files, including result.txt.
            with tempfile.TemporaryDirectory(prefix='swr-coroutine-original-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                for case in cases:
                    artifact = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name / Path(case['path']).with_suffix('')
                    try:
                        require_free_case_port(case)
                    except OSError as error:
                        record_result(report, engine, case, {'status': 'failed', 'detail': f'Fixed UDP9601 unavailable: {error}'})
                        save_report(args.output, report)
                        continue
                    results, timing = run_cases(engine, [case], sandbox, artifact, args.timeout, 1, offline=not args.external_network)
                    report['batches'].append({'engine': engine.name, **timing})
                    record_result(report, engine, case, results[case['path']])
                    save_report(args.output, report)
        report['execution_status'] = 'complete'
        report['passed'] = not unmeasured and bool(report['results']) and all(row['status'] == 'passed' for row in report['results'])
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
