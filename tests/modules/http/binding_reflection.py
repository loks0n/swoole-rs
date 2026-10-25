#!/usr/bin/env python3
"""Compare complete observed metadata for five HTTP PHP classes against native."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if len(engines) < 2 or engines[0].name != 'upstream':
        parser.error('First engine must be upstream=PATH, followed by at least one candidate')
    fixture = Path(__file__).with_suffix('.php')
    report = {'scope': 'Observed HTTP PHP metadata equivalence, including aliases and inherited methods; no runtime/lifetime/original-suite/performance or activation claim.',
              'engines': [], 'results': [], 'passed': False}
    baseline = None
    for index, engine in enumerate(engines):
        row = {'engine': engine.name, 'passed': False}
        report['results'].append(row)
        try:
            report['engines'].append(engine.metadata())
            command = engine.command(fixture)
            result = run_isolated(command, timeout=15)
            row.update(command=command, returncode=result.returncode,
                       stdout=result.stdout, stderr=result.stderr)
            if result.returncode:
                continue
            observed = json.loads(result.stdout)
            row.pop('stdout')
            row['metadata'] = observed
            if index == 0:
                baseline = observed
                row['passed'] = True
            else:
                row['passed'] = baseline is not None and baseline == observed
            row['method_appearances'] = {name: len(value['methods'])
                                        for name, value in observed['classes'].items()}
        except Exception as error:
            row['error'] = str(error)
    report['passed'] = all(row['passed'] for row in report['results'])
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'engines': len(engines)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
