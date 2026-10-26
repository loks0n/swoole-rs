#!/usr/bin/env python3
"""Watch this repository's CI and merge pull requests when it passes.

  ci.py merge PR             wait for the PR tier on the PR's head, then squash-merge
  ci.py wait [--commit SHA]  wait for a workflow run (default: the merge tier on main); a run
                             replaced by a newer push to main follows the newer run
  ci.py status [--commit SHA]  the same, without waiting

For the merge tier, failed phases come from its `phases` artifact, with new and fixed ones
against the previous completed run on main; other failures show each failed job's log tail.

Progress goes to stderr and the result to stdout (--json for machine output).
Exit codes: 0 passed or merged, 1 failed, 2 no run, still running or timed out, 3 cancelled,
4 the pull request conflicts with main or could not be merged.
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
# The merge-tier job whose dev.py phases the `phases` artifact lists, replacing its log tail.
PHASES_JOB = 'full-gates'


def gh(*args):
    return subprocess.run(['gh', *args], capture_output=True, text=True, check=True).stdout


def say(message):
    print(f'{datetime.now():%H:%M:%S} {message}', file=sys.stderr, flush=True)


def resolve(commit):
    return gh('api', 'repos/{owner}/{repo}/commits/' + (commit or 'main'), '-q', '.sha').strip()


def pr_head(number):
    return gh('pr', 'view', str(number), '--json', 'headRefOid', '-q', '.headRefOid').strip()


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


def phases(run):
    """{phase: passed} from a run's `phases` artifact (the merge tier's loop.json), or None without one."""
    with tempfile.TemporaryDirectory() as directory:
        try:
            gh('run', 'download', str(run), '-n', 'phases', '-D', directory)
        except subprocess.CalledProcessError:
            return None
        loop = next(Path(directory).rglob('loop.json'), None)
        return {row['phase']: not row['failed'] for row in json.loads(loop.read_text())['phases']} if loop else None


def phase_changes(result):
    """Failed phases, plus those new or fixed since the previous completed run on main that has phases."""
    current = phases(result['run'])
    if current is None:
        return result
    result = {**result, 'failed_phases': sorted(name for name, passed in current.items() if not passed)}
    runs = json.loads(gh('run', 'list', '--workflow', result['workflow'], '--branch', 'main', '--status', 'completed',
                         '--limit', '30', '--json', 'databaseId,conclusion,url'))
    for run in runs:
        previous = run['databaseId'] < result['run'] and run['conclusion'] in ('success', 'failure') and phases(run['databaseId'])
        if previous:
            return {**result, 'previous_run': run['url'],
                    'new_failures': [name for name in result['failed_phases'] if previous.get(name)],
                    'fixed': sorted(name for name, passed in current.items() if passed and previous.get(name) is False)}
    return result


def merge(number, workflow, deadline, poll):
    while True:
        head = pr_head(number)
        say(f'PR #{number}: waiting for {workflow} on {head[:7]}')
        result = wait(workflow, head, deadline, poll)
        if result['state'] == 'cancelled' and pr_head(number) != head:
            say(f'PR #{number}: run on {head[:7]} was superseded by a push; following the new head')
            continue
        if result['state'] != 'passed':
            return {**failure_logs(result), 'merged': False}
        # Merge only the commit that passed: --match-head-commit refuses if the branch moved.
        merged = subprocess.run(['gh', 'pr', 'merge', str(number), '--squash', '--match-head-commit', head],
                                capture_output=True, text=True)
        if merged.returncode == 0:
            sha = gh('pr', 'view', str(number), '--json', 'mergeCommit', '-q', '.mergeCommit.oid').strip()
            # Remote only: `gh pr merge --delete-branch` fails in a worktree that has the branch checked out.
            subprocess.run(['gh', 'api', '-X', 'DELETE', f'repos/{{owner}}/{{repo}}/git/refs/heads/{branch(number)}'],
                           capture_output=True)
            return {**result, 'merged': True, 'merge_commit': sha,
                    'next': f'python3 tools/ci.py wait --commit {sha}'}
        if pr_head(number) == head:
            conflict = gh('pr', 'view', str(number), '--json', 'mergeable', '-q', '.mergeable').strip() == 'CONFLICTING'
            return {**result, 'merged': False, 'conflict': conflict,
                    'error': 'conflicts with main: merge origin/main, push, and run ci.py merge again'
                    if conflict else merged.stderr.strip()}


def branch(number):
    return gh('pr', 'view', str(number), '--json', 'headRefName', '-q', '.headRefName').strip()


def hooks_warning():
    """None when this checkout's own .githooks run; worktrees may point at another checkout's copy."""
    git = lambda *args: subprocess.run(['git', *args], capture_output=True, text=True).stdout.strip()
    top, hooks = Path(git('rev-parse', '--show-toplevel')), git('config', 'core.hooksPath')
    fix = 'git config --worktree core.hooksPath .githooks' if git('rev-parse', '--git-dir') != git(
        'rev-parse', '--git-common-dir') else 'git config core.hooksPath .githooks'
    if not hooks:
        return f'git hooks are off; enable them with: {fix}'
    if (top / hooks).resolve() != (top / '.githooks').resolve():
        return f'git hooks run from {hooks}, not this checkout; fix with: {fix}'
    return None


def report(result, as_json):
    if as_json:
        print(json.dumps(result, indent=1))
        return
    line = f"{result['workflow']} {result['commit'][:7]}: {result['state']}"
    if 'merged' in result:
        line += ', merged as ' + result['merge_commit'][:7] if result['merged'] else ', not merged'
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
    if result.get('error'):
        print(result['error'])
    if result.get('merged'):
        print(f"Now watch the merge tier (every gate, application and PHPT): {result['next']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ['status', 'wait', 'merge']:
        command = commands.add_parser(name)
        if name == 'merge':
            command.add_argument('pr', type=int)
        else:
            command.add_argument('--commit', help='sha or branch (default: main)')
        command.add_argument('--workflow', default='pr.yml' if name == 'merge' else 'merge.yml')
        command.add_argument('--timeout', type=int, default=3600, help='seconds (default 3600)')
        command.add_argument('--poll', type=float, default=15, help=argparse.SUPPRESS)
        command.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    deadline = time.monotonic() + args.timeout
    try:
        if args.command == 'merge':
            warning = hooks_warning()
            if warning:
                say('warning: ' + warning)
            result = merge(args.pr, args.workflow, deadline, args.poll)
        else:
            sha = resolve(args.commit)
            result = status(args.workflow, sha) if args.command == 'status' else wait(args.workflow, sha, deadline, args.poll)
            if result['state'] in ('passed', 'failed'):
                result = failure_logs(phase_changes(result))
            if 'failed_phases' in result:
                result.get('logs', {}).pop(PHASES_JOB, None)
    except subprocess.CalledProcessError as failure:
        sys.exit(f"gh {' '.join(failure.cmd[1:])}: {failure.stderr.strip()}")
    report(result, args.json)
    if args.command == 'merge':
        return 0 if result['merged'] else 4 if 'error' in result else EXIT[result['state']]
    return 2 if result.get('timed_out') else EXIT[result['state']]


if __name__ == '__main__':
    sys.exit(main())
