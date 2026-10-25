#!/usr/bin/env python3
"""Isolated active-timer fork diagnostic, outside the original PHPT corpus."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, run_isolated, write_report


CASES = ('one-shot', 'persistent', 'child-reinit')


def expectation(case):
    child = 'DONE'
    if case == 'child-reinit':
        child = {'inherited_missing': True, 'initial_count': 0, 'clear': True,
                 'cleared_missing': True, 'cancelled_calls': 0, 'callbacks': 2,
                 'health': 1, 'timers': 0}
    return {'callbacks': 1 if case == 'one-shot' else 3, 'health': 1,
            'child_exit': 0, 'child_signal': 0, 'child_done': child, 'timers': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append')
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', default=str(ROOT / 'target/reports/timer-fork-active.json'))
    args = parser.parse_args()
    fixture = Path(__file__).with_suffix('.php')
    persistent = fixture.with_name('fork_persistent.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Active one-shot/repeating callback forks Swoole Process; child reset/reinitialization, parent repeated callback health and cleanup. Diagnostic separate from original PHPT corpus.',
              'engines': [], 'results': []}
    for engine in parse_engines(args.engine, args.php, args.php_extension):
        try:
            report['engines'].append(engine.metadata())
        except Exception as error:
            for case in args.case or CASES:
                report['results'].append({'engine': engine.name, 'case': case, 'status': 'failed',
                                          'detail': f'{type(error).__name__}: {error}'})
            continue
        for case in args.case or CASES:
            row = {'engine': engine.name, 'case': case}
            expected = expectation(case)
            try:
                command = engine.command(fixture) if case == 'one-shot' else engine.command(persistent, case)
                with tempfile.TemporaryDirectory(prefix='swr-active-fork-') as data:
                    result = run_isolated(command, timeout=10,
                                          env={**os.environ, 'TEST_DATA': data})
                row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                if result.returncode:
                    raise AssertionError('diagnostic process did not exit normally')
                # Preserve raw text even if native diagnostics precede final JSON.
                lines = result.stdout.splitlines()
                actual = json.loads(lines[-1])
                row['observed'] = actual
                if actual != expected:
                    raise AssertionError(f'expected {expected!r}; observed {actual!r}')
                row['status'] = 'passed'
            except Exception as error:
                row.update(status='failed', detail=f'{type(error).__name__}: {error}')
            report['results'].append(row)
            print(json.dumps(row), flush=True)
    write_report(args.output, report)
    return int(any(row['status'] != 'passed' for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
