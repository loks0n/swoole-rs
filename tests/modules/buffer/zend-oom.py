#!/usr/bin/env python3
"""Compare plain frame String allocation and real Zend fatal outcomes once per engine."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--output', default='target/reports/buffer-zend-oom.json')
    args = parser.parse_args()
    if len(args.engine) < 2: parser.error('Need a control and candidate engine')
    fixture = Path(__file__).with_suffix('.php')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Actual plain WebSocket String allocator; not codec migration, full memory safety, sanitizer-instrumented PHP, or phase-exact stack proof.',
              'engines': [], 'results': [], 'passed': True}
    baseline = {}
    for engine in parse_engines(args.engine, args.php):
        metadata = engine.metadata()
        report['engines'].append(metadata)
        for mode in ['success', 'fatal']:
            command = engine.command('-d', 'memory_limit=-1', fixture, mode)
            result = run_isolated(command, timeout=10)
            row = {'engine': engine.name, 'mode': mode, 'command': command, 'returncode': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr}
            if mode == 'success':
                try:
                    value = json.loads(result.stdout)
                    valid = result.returncode == 0 and not result.stderr and value['bytes'] == 4194304
                except (ValueError, KeyError):
                    valid = False
            else:
                valid = (result.returncode != 0 and 'SETUP ' in result.stdout and
                         'OPERATION plain-pack' in result.stdout and 'SHUTDOWN 1' in result.stdout and
                         'RETURN ' not in result.stdout and
                         'Allowed memory size' in result.stdout + result.stderr)
            observation = (result.returncode, result.stdout, result.stderr)
            matches = observation == baseline.setdefault(mode, observation)
            row.update(valid=valid, matches_first_engine=matches)
            report['results'].append(row)
            report['passed'] &= valid and matches
            write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'outcomes': [{k: r[k] for k in ['engine', 'mode', 'returncode', 'valid', 'matches_first_engine']} for r in report['results']]}))
    return 0 if report['passed'] else 1

if __name__ == '__main__': sys.exit(main())
