#!/usr/bin/env python3
"""Actual captured-PHP-object destructor exit/exception/OOM timer differential."""
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
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    cleanup = parser.add_mutually_exclusive_group()
    cleanup.add_argument('--idle-clear', action='store_true', help='Exercise clear/clearAll outside active selection')
    cleanup.add_argument('--event-exit', action='store_true', help='Exercise other timer destruction during Event::exit callback')
    parser.add_argument('--output', default='target/reports/timer-destructor-bailout.json')
    args = parser.parse_args()
    if len(args.engine) < 2:
        parser.error('First engine must be unchanged control, followed by candidate')
    outside = args.idle_clear or args.event_exit
    fixture = Path(__file__).with_name('destructor_clear.php') if outside else Path(__file__).with_suffix('.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Actual captured object destructor; exit/exception/OOM and coroutine off/on. Exact output/exit comparison. No modified original PHPT, sanitizer PHP or performance claim.',
              'cleanup': 'active Event::exit clears other timers' if args.event_exit else 'idle clear/clearAll' if args.idle_clear else 'successful after/tick callback',
              'engines': [], 'results': []}
    controls = {}
    try:
        for engine_index, engine in enumerate(parse_engines(args.engine, args.php)):
            report['engines'].append(engine.metadata())
            for kind in (['event-exit-after', 'event-exit-tick'] if args.event_exit else ['clear', 'clear-all'] if args.idle_clear else ['after', 'tick']):
                for coroutine in [0, 1]:
                    for mode in ['exit', 'throw', 'oom']:
                        key = (kind, coroutine, mode)
                        command = engine.command('-d', 'display_errors=stderr', fixture, kind, coroutine, mode)
                        row = {'engine': engine.name, 'kind': kind, 'coroutine': coroutine, 'mode': mode,
                               'command': command, 'passed': False}
                        try:
                            result = run_isolated(command, timeout=5)
                            row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                            valid = (result.returncode >= 0 and result.stdout.count('CALL\n') == (0 if outside else 1)
                                     and result.stdout.count('DTOR\n') == 1 and result.stdout.count('SHUTDOWN\n') == 1)
                            if mode == 'oom':
                                valid &= result.returncode == 255 and 'Allowed memory size' in result.stdout + result.stderr
                            observation = (result.returncode, result.stdout, result.stderr)
                            if engine_index == 0:
                                controls[key] = observation
                            control_available = key in controls
                            matches = control_available and observation == controls[key]
                            row.update(control_available=control_available, valid=bool(valid), matches_first_engine=matches, passed=bool(valid and matches))
                        except subprocess.TimeoutExpired as error:
                            row.update(error=str(error), stdout=str(error.stdout), stderr=str(error.stderr))
                        report['results'].append(row)
                        write_report(args.output, report)
        report['passed'] = len(report['results']) == len(report['engines']) * 12 and all(row['passed'] for row in report['results'])
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'results': len(report['results']),
                      'failures': [{k: r.get(k) for k in ['engine', 'kind', 'coroutine', 'mode', 'returncode', 'matches_first_engine', 'valid', 'error']} for r in report['results'] if not r['passed']]}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
