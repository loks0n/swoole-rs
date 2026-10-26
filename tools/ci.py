#!/usr/bin/env python3
"""Watch this repository's CI. GitHub merges pull requests itself (`gh pr merge --auto --squash`).

  ci.py wait [--commit SHA]  wait for a workflow run (default: the merge tier on main); a run
                             replaced by a newer push to main follows the newer run
  ci.py status [--commit SHA]  the same, without waiting

For a pull request: `ci.py wait --workflow pr.yml --commit BRANCH`.

For the merge tier, failed phases come from its `phases` artifact, with new and fixed ones
against the previous completed run on main; other failures show each failed job's log tail.

Progress goes to stderr and the result to stdout (--json for machine output).
Exit codes: 0 passed, 1 failed, 2 no run, still running or timed out, 3 cancelled.
Needs only `gh` (authenticated) and Python.
"""
import argparse
from datetime import datetime
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time

EXIT = {'passed': 0, 'failed': 1, 'none': 2, 'running': 2, 'cancelled': 3}
LOG_LINES = 40
# The merge-tier jobs (full-gates, or its shards "full-gates (N)") whose dev.py phases the
# `phases*` artifacts list, replacing their log tails.
PHASES_JOB = 'full-gates'


def gh(*args):
    return subprocess.run(['gh', *args], capture_output=True, text=True, check=True).stdout


def say(message):
    print(f'{datetime.now():%H:%M:%S} {message}', file=sys.stderr, flush=True)


def resolve(commit):
    return gh('api', 'repos/{owner}/{repo}/commits/' + (commit or 'main'), '-q', '.sha').strip()


def seconds(job):
    # GitHub reports unfinished timestamps as 0001-01-01T00:00:00Z.
    started, completed = (datetime.fromisoformat(job[key]) if job.get(key) and not job[key].startswith('0001')
                          else None for key in ('startedAt', 'completedAt'))
    return int((completed - started).total_seconds()) if started and completed else None


def status(workflow, sha):
    runs = json.loads(gh('run', 'list', '--workflow', workflow, '--commit', sha, '--limit', '1',
                         '--json', 'databaseId,status,conclusion,url'))
    if not runs:
        return {'workflow': workflow, 'commit': sha, 'state': 'none'}
    run = runs[0]
    state = ('running' if run['status'] != 'completed' else 'passed' if run['conclusion'] == 'success'
             else 'cancelled' if run['conclusion'] == 'cancelled' else 'failed')
    jobs = json.loads(gh('run', 'view', str(run['databaseId']), '--json', 'jobs'))['jobs']
    return {'workflow': workflow, 'commit': sha, 'state': state, 'run': run['databaseId'], 'url': run['url'],
            'jobs': [{'name': job['name'], 'state': job['conclusion'] or job['status'], 'seconds': seconds(job)}
                     for job in jobs]}


def successor(workflow, sha):
    """The newest run's head on main when it contains sha: the run that replaced sha's (latest wins)."""
    runs = json.loads(gh('run', 'list', '--workflow', workflow, '--branch', 'main', '--limit', '1', '--json', 'headSha'))
    head = runs[0]['headSha'] if runs else sha
    if head != sha and gh('api', f'repos/{{owner}}/{{repo}}/compare/{sha}...{head}', '-q', '.status').strip() == 'ahead':
        return head
    return None


def wait(workflow, sha, deadline, poll):
    """Wait for the run on sha to finish, reporting each job as its state changes. A run
    replaced by a newer push to main follows the newer run, which also covers sha."""
    seen, appear_by = {}, time.monotonic() + 300
    while True:
        result = status(workflow, sha)
        newer = result['state'] == 'cancelled' and successor(workflow, sha)
        if newer:
            say(f'{workflow} {sha[:7]}: replaced by the run on {newer[:7]}, which contains it')
            sha, seen = newer, {}
            continue
        for job in result.get('jobs', []):
            if seen.get(job['name']) != job['state']:
                seen[job['name']] = job['state']
                took = f" in {job['seconds']}s" if job['seconds'] is not None else ''
                say(f"{workflow} {sha[:7]} {job['name']}: {job['state']}{took}")
        if result['state'] not in ('running', 'none'):
            return result
        if result['state'] == 'none' and time.monotonic() > appear_by:
            return result
        if time.monotonic() > deadline:
            return {**result, 'timed_out': True}
        time.sleep(poll)


def failure_logs(result):
    """The tail of each failed job's log, so a failure can be read without another call."""
    if result['state'] != 'failed':
        return result
    try:
        log = gh('run', 'view', str(result['run']), '--log-failed')
    except subprocess.CalledProcessError:
        return result
    tails = {}
    for line in log.splitlines():
        job, _, text = line.partition('\t')
        tails.setdefault(job, []).append(text.partition('\t')[2] or text)
    return {**result, 'logs': {job: lines[-LOG_LINES:] for job, lines in tails.items()}}


def phases(run, tails=None):
    """{phase: passed} from a run's `phases*` artifacts (each shard's loop.json), or None without any.
    A phase every shard runs (the builds) passes only if it passed everywhere. Failed phases'
    log tails are added to `tails` when given."""
    with tempfile.TemporaryDirectory() as directory:
        try:
            gh('run', 'download', str(run), '-p', 'phases*', '-D', directory)
        except subprocess.CalledProcessError:
            return None
        loops = sorted(Path(directory).rglob('loop.json'))
        if not loops:
            return None
        passed = {}
        for loop in loops:
            for row in json.loads(loop.read_text())['phases']:
                passed[row['phase']] = passed.get(row['phase'], True) and not row['failed']
                if tails is not None and row.get('log_tail'):
                    tails[row['phase']] = row['log_tail']
        return passed


def phase_changes(result):
    """Failed phases, plus those new or fixed since the previous completed run on main that has phases."""
    tails = {}
    current = phases(result['run'], tails)
    if current is None:
        return result
    result = {**result, 'failed_phases': sorted(name for name, passed in current.items() if not passed)}
    runs = json.loads(gh('run', 'list', '--workflow', result['workflow'], '--branch', 'main', '--status', 'completed',
                         '--limit', '30', '--json', 'databaseId,conclusion,url'))
    for run in runs:
        previous = run['databaseId'] < result['run'] and run['conclusion'] in ('success', 'failure') and phases(run['databaseId'])
        if previous:
            # A phase the previous run didn't have is new too: it was added and fails on its first run.
            new = [name for name in result['failed_phases'] if previous.get(name) is not False]
            return {**result, 'previous_run': run['url'], 'new_failures': new,
                    'fixed': sorted(name for name, passed in current.items() if passed and previous.get(name) is False),
                    'phase_logs': {name: tails[name] for name in new if name in tails}}
    return result


def report(result, as_json):
    if as_json:
        print(json.dumps(result, indent=1))
        return
    line = f"{result['workflow']} {result['commit'][:7]}: {result['state']}"
    print(line + (' (timed out)' if result.get('timed_out') else '') + (f"  {result['url']}" if 'url' in result else ''))
    for job in result.get('jobs', []):
        print(f"  {job['name']}: {job['state']}" + (f" in {job['seconds']}s" if job['seconds'] is not None else ''))
    if 'failed_phases' in result:
        print(f"  failed phases ({len(result['failed_phases'])}): " + (', '.join(result['failed_phases']) or 'none'))
    if 'previous_run' in result:
        print(f"  since {result['previous_run']}: new failures: {', '.join(result['new_failures']) or 'none'}; "
              f"fixed: {', '.join(result['fixed']) or 'none'}")
    for job, lines in result.get('logs', {}).items():
        print(f'--- {job} (last {len(lines)} lines)', *lines, sep='\n')
    for name, lines in result.get('phase_logs', {}).items():
        print(f'--- new failure {name} (last {len(lines)} log lines)', *lines, sep='\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ['status', 'wait']:
        command = commands.add_parser(name)
        command.add_argument('--commit', help='sha or branch (default: main)')
        command.add_argument('--workflow', default='merge.yml')
        command.add_argument('--timeout', type=int, default=3600, help='seconds (default 3600)')
        command.add_argument('--poll', type=float, default=15, help=argparse.SUPPRESS)
        command.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.timeout
    try:
        sha = resolve(args.commit)
        result = status(args.workflow, sha) if args.command == 'status' else wait(args.workflow, sha, deadline, args.poll)
        if result['state'] in ('passed', 'failed'):
            result = failure_logs(phase_changes(result))
        if 'failed_phases' in result:
            for job in [job for job in result.get('logs', {}) if job.split(' (')[0] == PHASES_JOB]:
                result['logs'].pop(job)
    except subprocess.CalledProcessError as failure:
        sys.exit(f"gh {' '.join(failure.cmd[1:])}: {failure.stderr.strip()}")
    report(result, args.json)
    return 2 if result.get('timed_out') else EXIT[result['state']]


if __name__ == '__main__':
    sys.exit(main())
