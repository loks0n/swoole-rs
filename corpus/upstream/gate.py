#!/usr/bin/env python3
"""Merge sharded run.py reports and gate the hybrid on upstream.

Every PHPT that passes on upstream must pass on every other engine; anything else
exits 1. Tests failing on upstream too are reported, not hidden. Only the official
runner's PASSED counts as passed. Prints a Markdown summary; --output writes every
row as JSON.

A flagged test may be re-run (--recheck: reports of 3 re-runs per engine). If upstream
fails any re-run it is flaky on upstream; if upstream passes every re-run and another
engine fails any, it is a regression; if both pass every re-run, it passed on re-run.
Only regressions fail the gate, and a flagged test without re-runs stays one.
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
STATUSES = ['passed', 'failed', 'skipped']


def skip_reason(detail):
    match = re.search(r'reason:\s*(.*)', ANSI.sub('', detail or ''))
    return match.group(1).strip() if match else ''


def category(reason):
    lowered = reason.lower()
    return next((name for name, pattern in CATEGORIES if re.search(pattern, lowered)), 'other')


def rows(reports):
    for report in reports:
        data = json.loads(Path(report).read_text())
        if data.get('execution_status', 'complete') != 'complete':
            raise ValueError(f'{report}: run {data["execution_status"]}')
        for row in data['results']:
            entry = {'test': row['test'], 'family': row['module'], 'engine': row.get('engine', 'upstream'),
                     'status': row['status'], 'upstream_status': row.get('upstream_status')}
            if row['status'] == 'skipped':
                entry['reason'] = skip_reason(row.get('detail'))
                entry['category'] = category(entry['reason'])
            yield entry


def compare(results):
    """(regressions, failing on both): a missing result counts as not passed."""
    status = defaultdict(dict)
    for row in results:
        status[row['test']][row['engine']] = row['status']
    others = sorted({row['engine'] for row in results} - {'upstream'})
    regressions = sorted(f'{test} ({engine}: {engines.get(engine, "missing")})' for test, engines in status.items()
                         if engines.get('upstream') == 'passed' for engine in others if engines.get(engine) != 'passed')
    both = sorted(test for test, engines in status.items() if others and engines.get('upstream') == 'failed'
                  and all(engines.get(engine) == 'failed' for engine in others))
    return regressions, both


def flagged(results):
    """Tests that pass on upstream and not on some other engine."""
    return sorted({entry.split(' (')[0] for entry in compare(results)[0]})


def recheck(tests, rechecked):
    """(regressions, flaky on upstream, passed on re-run) for flagged tests, from their re-runs."""
    runs = defaultdict(lambda: defaultdict(list))
    for row in rechecked:
        runs[row['test']][row['engine']].append(row['status'])
    regressions, flaky, recovered = [], [], []
    for test in tests:
        upstream = runs[test].get('upstream', [])
        others = [status for engine, statuses in runs[test].items() if engine != 'upstream' for status in statuses]
        if not upstream or not others:
            regressions.append(test)
        elif any(status != 'passed' for status in upstream):
            flaky.append(test)
        elif any(status != 'passed' for status in others):
            regressions.append(test)
        else:
            recovered.append(test)
    return regressions, flaky, recovered


def listing(title, tests):
    return [f'<details><summary>{len(tests)} {title}</summary>', '', *[f'- `{test}`' for test in tests], '', '</details>', '']


def markdown(results, rechecked=None):
    engines = sorted({row['engine'] for row in results}, key=lambda engine: (engine != 'upstream', engine))
    families = defaultdict(Counter)
    for row in results:
        families[row['family']][row['engine'], row['status']] += 1
    lines = []
    for engine in engines:
        statuses = Counter(row['status'] for row in results if row['engine'] == engine)
        skips = Counter(row['category'] for row in results if row['engine'] == engine and row['status'] == 'skipped')
        lines += [f'**{sum(statuses.values())} PHPTs** on {engine}: ' + ', '.join(f'{statuses[s]} {s}' for s in STATUSES),
                  '', 'Skips by reason: ' + ', '.join(f'{n} {c}' for c, n in skips.most_common()), '']
    regressions, both = compare(results)
    if len(engines) > 1 and rechecked is not None:
        confirmed, flaky, recovered = recheck(flagged(results), rechecked)
        lines += listing('regressions: pass on upstream, fail on a re-run here', confirmed)
        lines += listing('flaky on upstream (failed on an upstream re-run; not gated)', flaky)
        lines += listing('passed on re-run on both engines (not gated)', recovered)
        lines += listing('failing on upstream too', both)
    elif len(engines) > 1:
        lines += listing('passing on upstream but not here (regressions)', regressions)
        lines += listing('failing on upstream too', both)
    lines += ['| Family | ' + ' | '.join(f'{e} {s}' for e in engines for s in STATUSES) + ' |',
              '| --- |' + ' --- |' * (len(engines) * len(STATUSES))]
    lines += [f'| {family} | ' + ' | '.join(str(c[e, s]) for e in engines for s in STATUSES) + ' |'
              for family, c in sorted(families.items())]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--recheck', type=Path, nargs='+', help='Reports of re-runs of the flagged tests')
    parser.add_argument('--print-regressions', action='store_true', help='Print flagged test paths and exit')
    args = parser.parse_args()
    results = sorted(rows(args.reports), key=lambda row: (row['test'], row['engine']))
    if args.print_regressions:
        print('\n'.join(flagged(results)))
        return 0
    rechecked = list(rows(args.recheck)) if args.recheck else None
    if args.output:
        args.output.write_text(json.dumps(results, indent=1) + '\n')
    print(markdown(results, rechecked))
    if rechecked is not None:
        return int(bool(recheck(flagged(results), rechecked)[0]))
    return int(bool(compare(results)[0]))


if __name__ == '__main__':
    sys.exit(main())
