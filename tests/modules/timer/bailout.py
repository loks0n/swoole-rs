#!/usr/bin/env python3
"""Actual PHP timer callback fatal/exit/exception teardown, strict matched controls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True, help='First engine is unchanged upstream control')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', default='target/reports/timer-bailout.json')
    args = parser.parse_args()
    if len(args.engine) < 2:
        parser.error('Need upstream control and candidate')
    fixture = Path(__file__).with_suffix('.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Actual PHP callback after/tick, coroutine on/off, exit/exception/fatal OOM and shutdown-visible timer state. No original PHPT changed; no sanitizer or Rust-frame stack proof.',
              'engines': [], 'results': []}
    controls = {}
    try:
        for engine_index, engine in enumerate(parse_engines(args.engine, args.php, args.php_extension)):
            report['engines'].append(engine.metadata())
            for kind in ['after', 'tick']:
                for coroutine in [0, 1]:
                    # Exit and converted exceptions can return to the native loop;
                    # always clear them. Fatal OOM must also preserve uncleared state.
                    for mode, clear in [('exit', 1), ('throw', 1), ('oom', 1), ('oom', 0)]:
                        key = (kind, coroutine, mode, clear)
                        command = engine.command('-d', 'memory_limit=-1', fixture, kind, mode, coroutine, clear)
                        row = {'engine': engine.name, 'kind': kind, 'coroutine': coroutine,
                               'mode': mode, 'clear': clear, 'command': command, 'passed': False}
                        try:
                            result = run_isolated(command, timeout=5)
                            row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                            valid = (result.returncode >= 0 and result.stdout.count('CALL\n') == 1
                                     and result.stdout.count('SHUTDOWN ') == 1 and 'STATE ' in result.stdout)
                            if mode == 'oom':
                                valid &= (result.returncode == 255 and 'SHUTDOWN 1\n' in result.stdout
                                          and 'Allowed memory size' in result.stdout + result.stderr)
                            observation = (result.returncode, result.stdout, result.stderr)
                            if engine_index == 0:
                                controls[key] = observation
                            control_available = key in controls
                            matches = control_available and observation == controls[key]
                            row.update(control_available=control_available, valid=valid, matches_first_engine=matches, passed=bool(valid and matches))
                        except subprocess.TimeoutExpired as error:
                            row.update(error=str(error), stdout=str(error.stdout), stderr=str(error.stderr))
                        report['results'].append(row)
                        write_report(args.output, report)
        report['passed'] = len(report['results']) == len(report['engines']) * 16 and all(row['passed'] for row in report['results'])
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'results': len(report['results']),
                      'failures': [{k: row.get(k) for k in ['engine', 'kind', 'coroutine', 'mode', 'clear', 'returncode', 'valid', 'matches_first_engine', 'error']} for row in report['results'] if not row['passed']]}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
