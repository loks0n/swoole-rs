#!/usr/bin/env python3
"""Compare Appwrite e2e JUnit reports: hybrid against stock (upstream) Swoole.

Reads DIR/junit-<variant>-<service>/junit.xml as appwrite-e2e.yml uploads them.
Fails when a test passes on upstream but fails, errors or is missing on the hybrid,
or when a service has an upstream report and no hybrid one. Tests failing on
upstream are listed as not gated. Prints a Markdown summary.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def outcomes(path):
    """{test id: 'passed' | 'failed' | 'skipped'} for one JUnit file."""
    result = {}
    for case in ET.parse(path).iter('testcase'):
        name = f"{case.get('class') or case.get('classname')}::{case.get('name')}"
        if case.find('failure') is not None or case.find('error') is not None:
            result[name] = 'failed'
        elif case.find('skipped') is not None:
            result[name] = 'skipped'
        else:
            result[name] = 'passed'
    return result


def load(directory):
    """{variant: {service: outcomes}}."""
    reports = defaultdict(dict)
    for path in sorted(Path(directory).glob('junit-*/junit.xml')):
        _, variant, service = path.parent.name.split('-', 2)
        reports[variant][service] = outcomes(path)
    return reports


def compare(reports):
    """(regressions, upstream failures, missing hybrid services, per-service counts)."""
    regressions, flaky, missing, counts = [], [], [], {}
    hybrid = reports.get('hybrid', {})
    for service, stock in sorted(reports.get('upstream', {}).items()):
        if service not in hybrid:
            missing.append(service)
            continue
        ours = hybrid[service]
        for test, outcome in sorted(stock.items()):
            if outcome == 'failed':
                flaky.append(f'{service}: {test}')
            elif outcome == 'passed' and ours.get(test, 'missing') in ('failed', 'missing'):
                regressions.append(f'{service}: {test} ({ours.get(test, "missing")})')
        counts[service] = tuple(sum(1 for o in r.values() if o == 'passed') for r in (stock, ours))
    return regressions, flaky, missing, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    regressions, flaky, missing, counts = compare(load(args.directory))
    print('| service | upstream passed | hybrid passed |\n| --- | --- | --- |')
    for service, (stock, ours) in counts.items():
        print(f'| {service} | {stock} | {ours} |')
    for title, items in [('Regressions (pass on upstream, not on hybrid)', regressions),
                         ('Services without a hybrid report', missing),
                         ('Failing on upstream (not gated)', flaky)]:
        print(f'\n### {title}: {len(items)}')
        print(''.join(f'- {item}\n' for item in items), end='')
    return 1 if regressions or missing or not counts else 0


if __name__ == '__main__':
    sys.exit(main())
