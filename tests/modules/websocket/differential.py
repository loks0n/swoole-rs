#!/usr/bin/env python3
"""Compare deterministic real PHP WebSocket frame outcomes between two engines."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-differential.json'))
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if len(engines) != 2:
        parser.error('Provide exactly two --engine NAME=extension options')
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'scope': '58 original FIN/mask cases plus576 PHP string/object lifetime cases and144 pack-only control RSV1 compatibility cases',
              'engines': [engine.metadata() for engine in engines],
              'expected_cases': 778, 'results': [], 'differences': []}
    for engine in engines:
        result = run_isolated(engine.command(Path(__file__).with_suffix('.php')), timeout=30)
        try:
            outcome = json.loads(result.stdout)
        except json.JSONDecodeError:
            outcome = {'cases': {}, 'errors': {'process': 'Invalid JSON: ' + result.stdout}}
        report['results'].append({'engine': engine.name, 'returncode': result.returncode,
                                  'stderr': result.stderr, **outcome})
    left, right = report['results']
    for case in sorted(left['cases'].keys() | right['cases'].keys()):
        if left['cases'].get(case) != right['cases'].get(case):
            report['differences'].append(case)
    failed = any(row['returncode'] or row['errors'] or len(row['cases']) != 778
                 for row in report['results']) or bool(report['differences'])
    report['passed'] = not failed
    write_report(args.output, report)
    print(f'{len(left["cases"])} cases; {len(report["differences"])} differences; passed={not failed}; {args.output}')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
