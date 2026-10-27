#!/usr/bin/env python3
"""Merge sharded run.py reports and gate the hybrid on upstream.

Every PHPT that passes on upstream must pass on every other engine; anything else
exits 1. Tests failing on upstream too are reported, not hidden. Only the official
runner's PASSED counts as passed. Prints a Markdown summary; --output writes every
row as JSON.

A flagged test may be re-run (--recheck: up to 3 re-runs per engine, or one hybrid
re-run when the hybrid's first failure timed out). If upstream fails a re-run, the test
is flaky on upstream only if the hybrid passes one of its re-runs; otherwise it is a
regression. If upstream passes every re-run, any failed hybrid re-run is a regression
and passing them all is a pass on re-run. Only regressions fail the gate, and a flagged
test without hybrid re-runs stays one.
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
# PHP's run-tests timeout marker, and run.py's own group deadline.
TIMED_OUT = re.compile(r'process timed out|exceeded its isolated group deadline')
RERUNS = 3
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
            elif row['status'] == 'failed':
                entry['timed_out'] = bool(TIMED_OUT.search(row.get('detail') or ''))
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


def reruns(rechecked):
    runs = defaultdict(lambda: defaultdict(list))
    for row in rechecked:
        runs[row['test']][row['engine']].append(row['status'])
    return runs


def recheck(tests, rechecked):
    """(regressions, flaky on upstream, passed on re-run) for flagged tests, from their re-runs."""
    runs = reruns(rechecked)
    regressions, flaky, recovered = [], [], []
    for test in tests:
        upstream = runs[test].get('upstream', [])
        others = [status for engine, statuses in runs[test].items() if engine != 'upstream' for status in statuses]
        if any(status != 'passed' for status in upstream):
            # Upstream is noisy; only a hybrid pass shows the hybrid isn't simply broken.
            (flaky if 'passed' in others else regressions).append(test)
        elif not upstream or not others or any(status != 'passed' for status in others):
            regressions.append(test)
        else:
            recovered.append(test)
    return regressions, flaky, recovered


def pending(tests, rechecked, engine='upstream', results=()):
    """Flagged tests still worth re-running on `engine`. Upstream stops at its first failed
    re-run. Another engine stops once its verdict is settled (a pass after an upstream
    failure, a failure otherwise) or its budget is spent: one re-run if its first failure
    timed out, else three."""
    runs = reruns(rechecked)
    if engine == 'upstream':
        return [test for test in tests if all(status == 'passed' for status in runs[test].get('upstream', []))]
    timed_out = {row['test'] for row in results if row['engine'] == engine and row.get('timed_out')}
    left = []
    for test in tests:
        statuses = runs[test].get(engine, [])
        settled = 'passed' if any(status != 'passed' for status in runs[test].get('upstream', [])) else 'failed'
        if settled not in statuses and len(statuses) < (1 if test in timed_out else RERUNS):
            left.append(test)
    return left


def flaky_listing(tests, rechecked):
    runs = reruns(rechecked)
    lines = [f'<details><summary>{len(tests)} flaky on upstream (failed an upstream re-run, hybrid passed one; not gated)</summary>', '']
    for test in tests:
        lines.append(f'- `{test}`: ' + '; '.join(f'{engine} {", ".join(statuses)}' for engine, statuses in sorted(runs[test].items())))
    return lines + ['', '</details>', '']


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
        lines += flaky_listing(flaky, rechecked)
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
    parser.add_argument('--print-pending', metavar='ENGINE',
                        help='Print flagged tests still worth re-running on ENGINE (with --recheck), and exit')
    args = parser.parse_args()
    results = sorted(rows(args.reports), key=lambda row: (row['test'], row['engine']))
    if args.print_regressions:
        print('\n'.join(flagged(results)))
        return 0
    rechecked = list(rows(args.recheck)) if args.recheck else None
    if args.print_pending:
        print('\n'.join(pending(flagged(results), rechecked or [], args.print_pending, results)))
        return 0
    if args.output:
        args.output.write_text(json.dumps(results, indent=1) + '\n')
    print(markdown(results, rechecked))
    if rechecked is not None:
        return int(bool(recheck(flagged(results), rechecked)[0]))
    return int(bool(compare(results)[0]))


if __name__ == '__main__':
    sys.exit(main())
