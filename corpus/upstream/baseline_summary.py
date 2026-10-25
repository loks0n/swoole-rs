#!/usr/bin/env python3
"""Merge sharded run.py reports into one baseline: every PHPT's result, skip reason and why.

Only the official runner's PASSED counts as passed. Prints a Markdown summary;
--output writes every row as JSON.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

# First match wins; the reason is the official runner's SKIPIF text.
CATEGORIES = [
    ('service', r'mysql|redis|pgsql|postgres|mongo|database|ftp|ssh|httpbin|docker|kafka|odbc|oracle'),
    ('network', r'online|offline|internet|network|dns|ipv6|proxy'),
    ('zts', r'\bn?zts\b|\bnts\b|thread'),
    ('stdext', r'stdext'),
    ('platform', r'darwin|macos|linux|windows|freebsd|arm|x86|io_uring|root'),
    ('extension', r'extension|not exist|not loaded|not support'),
]
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def skip_reason(detail):
    match = re.search(r'reason:\s*(.*)', ANSI.sub('', detail or ''))
    return match.group(1).strip() if match else ''


def category(reason):
    lowered = reason.lower()
    return next((name for name, pattern in CATEGORIES if re.search(pattern, lowered)), 'other')


def rows(reports):
    for report in reports:
        for row in json.loads(Path(report).read_text())['results']:
            entry = {'test': row['test'], 'family': row['module'], 'status': row['status'],
                     'upstream_status': row.get('upstream_status')}
            if row['status'] == 'skipped':
                entry['reason'] = skip_reason(row.get('detail'))
                entry['category'] = category(entry['reason'])
            yield entry


def markdown(results):
    statuses = Counter(row['status'] for row in results)
    skips = Counter(row['category'] for row in results if row['status'] == 'skipped')
    families = defaultdict(Counter)
    for row in results:
        families[row['family']][row['status']] += 1
    lines = [f'**{len(results)} PHPTs** on upstream: ' + ', '.join(f'{statuses[s]} {s}' for s in ['passed', 'failed', 'skipped']),
             '', 'Skips by reason: ' + ', '.join(f'{n} {c}' for c, n in skips.most_common()), '',
             '| Family | Passed | Failed | Skipped |', '| --- | --- | --- | --- |']
    lines += [f'| {family} | {c["passed"]} | {c["failed"]} | {c["skipped"]} |' for family, c in sorted(families.items())]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = sorted(rows(args.reports), key=lambda row: row['test'])
    if args.output:
        args.output.write_text(json.dumps(results, indent=1) + '\n')
    print(markdown(results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
