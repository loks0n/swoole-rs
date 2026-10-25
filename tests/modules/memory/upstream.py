#!/usr/bin/env python3
"""Inventory/run all pinned original table PHPTs with the shared official runner."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import ROOT, parse_engines, run_isolated

HEAVY = {'bug_2290': '1024 rows with a 512 KiB column',
         'random_bytes': 'up to 2048 rows with a 256 KiB column and randomized payload writes'}
PRIORITY = ['getMemorySize_1', 'incr_after_del', 'set_after_del', 'del', 'foreach',
            'stats', 'force_unlock', 'get_before_create', 'get_after_destroy']


def inventory(source):
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if pin != COMMIT:
        raise ValueError('Table source HEAD differs from the pinned commit')
    paths = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-r', '--name-only',
                                    COMMIT, 'tests/swoole_table'], text=True).splitlines()
    cases = []
    for path in sorted(path for path in paths if path.endswith('.phpt')):
        body = subprocess.check_output(['git', '-C', str(source), 'show', f'{COMMIT}:{path}'])
        name = Path(path).stem
        required = ['table', 'upstream_test_bootstrap']
        if b'Process' in body:
            required.append('processes')
        if b'SOCK_STREAM' in body:
            required.append('php_sockets')
        cases.append({'path': path, 'module': 'table', 'sha256': hashlib.sha256(body).hexdigest(),
                      'requires': required, 'resource_note': HEAVY.get(name),
                      'priority': name in PRIORITY})
    if len(cases) != 19 or not set(PRIORITY + list(HEAVY)) <= {Path(case['path']).stem for case in cases}:
        raise ValueError('Pinned 19-case inventory changed; review the selection')
    return sorted(cases, key=lambda case: (PRIORITY.index(Path(case['path']).stem)
                  if Path(case['path']).stem in PRIORITY else len(PRIORITY), case['path']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--engine', action='append', default=[])
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--require-memory-bridge', action='append', default=[], metavar='ENGINE')
    parser.add_argument('--case', action='append', default=[], help='Exact original basename; explicit heavy cases are included')
    parser.add_argument('--include-heavy', action='store_true')
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--timeout', type=int, default=45)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/memory-table-upstream.json')
    args = parser.parse_args()
    if args.timeout < 1 or not args.inventory_only and not args.engine:
        parser.error('Require a positive timeout and --engine unless --inventory-only')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': COMMIT,
              'scope': 'Original table PHPT bodies/SKIPIF/assertions/expectations unchanged; serial official shared runner/support adapter in disposable trees. Inventory completeness and selected-case passes are separate.',
              'support_adapter': 'corpus/upstream/README.md: local helper autoload and unrelated remote-object initialization exclusion only',
              'coverage_gaps': ['No original table PHPT directly checks duplicate column declarations; native differential and separate new PHP state witness cover first-lookup/accounting behavior.'],
              'passed': False, 'whole_inventory_passed': False, 'execution_status': 'running',
              'engines': [], 'results': [], 'batches': [], 'additional_module_checks': []}
    try:
        cases = inventory(args.source)
        unknown = set(args.case) - {Path(case['path']).stem for case in cases}
        if unknown:
            raise ValueError('Unknown table case: ' + ', '.join(sorted(unknown)))
        selected, omitted = [], []
        for case in cases:
            name = Path(case['path']).stem
            reason = ('Outside explicit --case selection' if args.case and name not in args.case
                      else 'High-memory case requires --include-heavy or exact --case'
                      if not args.case and name in HEAVY and not args.include_heavy else None)
            (omitted if reason else selected).append({**case, 'not_run_reason': reason} if reason else case)
        report.update(inventory=cases, inventory_count=len(cases), selected_cases=selected,
                      unmeasured_cases=omitted)
        if args.inventory_only:
            report['execution_status'] = 'inventory_only'
            save_report(args.output, report)
            print(json.dumps({'inventory_count': len(cases), 'selected': len(selected), 'unmeasured': len(omitted), 'tests_run': 0}))
            return 0
        engines = parse_engines(args.engine, args.php, args.php_extension)
        if set(args.require_memory_bridge) - {engine.name for engine in engines}:
            raise ValueError('Unknown --require-memory-bridge engine')
        for engine in engines:
            metadata = engine.metadata()
            report['engines'].append(metadata)
            if engine.name in args.require_memory_bridge and not (metadata['rust_feature_bits'] & 64):
                raise ValueError(f'{engine.name} does not advertise the required memory bit 64')
            with tempfile.TemporaryDirectory(prefix='swr-memory-original-') as directory:
                sandbox = Path(directory)
                prepare(args.source, sandbox, selected)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                for case in selected:
                    missing = set(case['requires']) - set(metadata['capabilities'])
                    if missing:
                        result = {'status': 'unsupported', 'missing_dependencies': sorted(missing),
                                  'detail': 'Required APIs unavailable; original body not run'}
                    else:
                        artifact = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name / Path(case['path']).stem
                        rows, timing = run_cases(engine, [case], sandbox, artifact, args.timeout, 1)
                        report['batches'].append({'engine': engine.name, **timing})
                        result = rows[case['path']]
                    record_result(report, engine, case, result)
                    save_report(args.output, report)
                for filename, required, scope in [
                    ('table_state.php', {'table'}, 'New PHP layout/duplicate-column witness'),
                    ('table_fork.php', {'table', 'processes'}, 'New PHP fork/column-index destruction witness'),
                    ('table_storage.php', {'table', 'processes'}, 'New PHP odd-width logical memory/iteration/fork witness'),
                    ('table_clear_batches.php', {'table', 'processes'}, 'New PHP multi-batch clear/reuse/float-zero/fork witness'),
                ]:
                    witness = Path(__file__).with_name(filename)
                    missing = required - set(metadata['capabilities'])
                    if missing:
                        observation = {'status': 'unsupported', 'detail': 'Missing witness APIs: ' + ', '.join(sorted(missing))}
                    else:
                        run = run_isolated(engine.command(witness), cwd=sandbox, timeout=30)
                        observation = {'status': 'failed', 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
                        if run.returncode == 0 and not run.stderr:
                            observation.update(status='passed', values=json.loads(run.stdout))
                    report['additional_module_checks'].append({'engine': engine.name, 'name': filename,
                        'scope': scope + ', not an original PHPT', **observation})
                    save_report(args.output, report)
        groups = {filename: [row['values'] for row in report['additional_module_checks']
                            if row['name'] == filename and row['status'] == 'passed']
                  for filename in ['table_state.php', 'table_fork.php', 'table_storage.php', 'table_clear_batches.php']}
        report['module_observations_match'] = all(len(values) == len(engines)
            and all(value == values[0] for value in values) for values in groups.values())
        report['module_observations_compared'] = len(engines) > 1 and all(len(values) == len(engines) for values in groups.values())
        report['execution_status'] = 'complete'
        report['passed'] = bool(selected) and len(report['results']) == len(selected) * len(engines) and all(row['status'] == 'passed' for row in report['results']) and all(row['status'] == 'passed' for row in report['additional_module_checks']) and report['module_observations_match']
        report['whole_inventory_passed'] = report['passed'] and not omitted
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['execution_status'] = 'failed'
    finally:
        if report['execution_status'] == 'running':
            report['execution_status'] = 'interrupted'
        report['summary'] = dict(Counter(row['status'] for row in report['results']))
        save_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'whole_inventory_passed', 'summary', 'error']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
