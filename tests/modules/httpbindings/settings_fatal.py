#!/usr/bin/env python3
"""Preserve actual native fatal/exception startup outcomes outside Rust frames."""
import argparse
import json
import os
import re
from pathlib import Path
import sys
import tempfile
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
        parser.error('First engine upstream=PATH plus candidate engine(s) required')
    fixture = Path(__file__).with_suffix('.php')
    report = {'scope': __doc__, 'limitations': 'Supplemental expected fatal/exception controls preserve nonzero child outcomes. Not original PHPT passes or full bailout/GC/lifetime proof.',
              'engines': [], 'cases': [], 'errors': [], 'passed': False}
    baseline = {}
    cases = ['types-false', 'types-string', 'types-number', 'bad-upload', 'throw-upload']
    try:
        for index, engine in enumerate(engines):
            report['engines'].append(engine.metadata())
            for case in cases:
                with tempfile.TemporaryDirectory(prefix='swr-startup-error-') as data:
                    command = engine.command(fixture)
                    result = run_isolated(command, timeout=10, env={**os.environ, 'HTTPBINDINGS_FATAL_CASE': case, 'TEST_DATA': data})
                    raw = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
                    observed = {key: re.sub(r'\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d %\d+\.\d+\]', '[runtime]', value.replace(data, '<TEST_DATA>')) if isinstance(value, str) else value for key, value in raw.items()}
                    assert 'settings-start' in result.stdout
                    combined = result.stdout + result.stderr
                    if case.startswith('types-'):
                        assert result.returncode != 0 and 'http_compression_types must be array' in combined
                    elif case == 'bad-upload':
                        assert result.returncode != 0 and 'Unable to create upload_tmp_dir' in combined
                        assert '/nested-error' in combined
                    else:
                        assert 'conversion rejected' in combined and '/nested-error' in combined
                    if index == 0:
                        baseline[case] = observed
                    assert observed == baseline[case], (case, observed, baseline[case])
                    report['cases'].append({'engine': engine.name, 'case': case, 'raw_outcome': raw,
                                            'normalized_outcome': observed, 'native_outcome_preserved': True,
                                            'normalization': 'Private directory and runtime log timestamp/PID prefix only; all warning/error text and raw exits retained'})
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    report['passed'] = not report['errors'] and len(report['cases']) == len(cases) * len(engines)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
