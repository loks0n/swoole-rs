#!/usr/bin/env python3
"""Whole pinned runtime/socket/system/io_uring PHPT inventory; original assertions and official runner."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import ROOT, parse_engines

GROUPS = {'swoole_runtime': 147, 'swoole_socket_coro': 62, 'swoole_coroutine_system': 18, 'swoole_iouring': 2}


def selection(source, groups=(), names=()):
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if pin != COMMIT:
        raise ValueError('Hooks source HEAD differs from frozen pin')
    inventory = []
    for group, count in GROUPS.items():
        paths = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only', COMMIT,
                                        'tests/' + group], text=True).splitlines()
        paths = sorted(path for path in paths if path.endswith('.phpt'))
        if len(paths) != count:
            raise ValueError('Pinned hooks original inventory differs: ' + group)
        for path in paths:
            original = subprocess.check_output(['git', '-C', str(source), 'show', f'{COMMIT}:{path}'])
            inventory.append({'path': path, 'module': 'hooks', 'group': group,
                              'sha256': hashlib.sha256(original).hexdigest()})
    if set(names) - {case['path'] for case in inventory}:
        raise ValueError('Unknown exact original --case path')
    selected = [case for case in inventory if (not groups or case['group'] in groups) and (not names or case['path'] in names)]
    if not selected:
        raise ValueError('No hooks cases selected')
    return inventory, selected



def support_inventory(source):
    # Preserve every pinned non-PHPT helper in these four original groups, plus
    # original data used through SOURCE_ROOT_PATH/TEST_IMAGE. No assertion edits.
    names = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only', COMMIT,
                                    *['tests/' + group for group in GROUPS]], text=True).splitlines()
    names = sorted({name for name in names if not name.endswith('.phpt')} |
                   {'README.md', 'package.xml', 'examples/test.jpg'})
    return [{'path': name, 'sha256': hashlib.sha256(subprocess.check_output(
        ['git', '-C', str(source), 'cat-file', 'blob', f'{COMMIT}:{name}'])).hexdigest()}
            for name in names]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--external-network', action='store_true', help='Include original external-network cases without changing probes')
    parser.add_argument('--case', action='append', default=[], help='Exact pinned tests/... relative path; default selects all229')
    parser.add_argument('--group', action='append', choices=sorted(GROUPS), default=[])
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/hooks-upstream.json')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': COMMIT,
              'scope': 'Original pinned runtime/socket/system/io_uring PHPTs, serial isolated official runner; no assertion or expected-output changes.',
              'inventory_count': 229, 'engines': [], 'results': [], 'batches': [],
              'passed': False, 'execution_status': 'running'}
    try:
        inventory, cases = selection(args.source, args.group, args.case)
        unmeasured = [case['path'] for case in inventory if case not in cases]
        report['inventory'] = inventory
        support_files = support_inventory(args.source)
        report['support_files'] = support_files
        report.update(selected_cases=[case['path'] for case in cases], unmeasured_cases=unmeasured)
        save_report(args.output, report)
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            report['engines'].append(engine.metadata())
            # Each engine gets fresh disposable support files, including result.txt.
            with tempfile.TemporaryDirectory(prefix='swr-hooks-original-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases, support_files=support_files)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                for case in cases:
                    artifact = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name / Path(case['path']).with_suffix('')
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
