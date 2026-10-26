"""tools/ci.py against a fake gh: run states, merging only the head that passed, following superseded runs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
# Runs are scripted per head in FAKE_RUNS: {sha: [conclusion, ...]}, one entry
# consumed per `run list`; the PR head advances through FAKE_HEADS on each run list.
FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ['FAKE_STATE'])
data = json.loads(state.read_text())
with open(os.environ['FAKE_GH_LOG'], 'a') as log:
    log.write(' '.join(args) + '\\n')
def save():
    state.write_text(json.dumps(data))
if args[0] == 'api' and '-X' in args:
    pass
elif args[0] == 'api':
    print('c' * 40)
elif args[:2] == ['pr', 'view']:
    field = args[args.index('--json') + 1]
    print({'headRefOid': data['heads'][0], 'mergeCommit': 'm' * 40, 'headRefName': 'topic',
           'mergeable': data.get('mergeable', 'MERGEABLE')}[field])
elif args[:2] == ['pr', 'merge']:
    sys.exit(data.get('merge_exit', 0))
elif args[:2] == ['run', 'list'] and '--commit' not in args:
    print(json.dumps(data.get('history', [])))
elif args[:2] == ['run', 'download']:
    rows = data.get('phases', {}).get(args[2])
    if rows is None:
        sys.exit(1)
    loop = Path(args[args.index('-D') + 1]) / 'target/reports/dev/x/loop.json'
    loop.parent.mkdir(parents=True)
    loop.write_text(json.dumps({'phases': [{'phase': name, 'failed': not passed} for name, passed in rows]}))
elif args[:2] == ['run', 'list']:
    sha = args[args.index('--commit') + 1]
    queue = data['runs'].get(sha, [])
    conclusion = queue.pop(0) if len(queue) > 1 else (queue[0] if queue else None)
    if conclusion == 'cancelled' and len(data['heads']) > 1:
        data['heads'].pop(0)
    save()
    if conclusion is not None:
        running = conclusion == 'running'
        print(json.dumps([{'databaseId': 7, 'status': 'in_progress' if running else 'completed',
                           'conclusion': '' if running else conclusion, 'url': 'u'}]))
    else:
        print('[]')
elif args[:2] == ['run', 'view'] and '--log-failed' in args:
    print('rust\\tcargo test\\t2026-10-25T21:00:01Z error: boom')
elif args[:2] == ['run', 'view']:
    print(json.dumps({'jobs': [{'name': 'rust', 'status': 'completed', 'conclusion': 'success',
                                'startedAt': '2026-10-25T21:00:00Z', 'completedAt': '2026-10-25T21:00:31Z'}]}))
'''


class Ci(unittest.TestCase):
    def ci(self, *args, runs, heads=('a' * 40,), **extra):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / 'gh'
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            state, log = Path(temp) / 'state.json', Path(temp) / 'gh.log'
            state.write_text(json.dumps({'runs': runs, 'heads': list(heads), **extra}))
            env = {**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH'],
                   'FAKE_STATE': str(state), 'FAKE_GH_LOG': str(log)}
            result = subprocess.run([sys.executable, ROOT / 'tools/ci.py', *args, '--poll', '0', '--json'],
                                    env=env, capture_output=True, text=True)
            self.gh_calls = log.read_text().splitlines() if log.exists() else []
        return result.returncode, json.loads(result.stdout or '{}'), result.stderr

    def test_merges_the_head_that_passed_and_points_at_the_merge_tier(self):
        code, result, _ = self.ci('merge', '12', runs={'a' * 40: ['running', 'success']})
        self.assertEqual((code, result['merged']), (0, True))
        self.assertIn('pr merge 12 --squash --match-head-commit ' + 'a' * 40, self.gh_calls)
        self.assertEqual(result['next'], 'python3 tools/ci.py wait --commit ' + 'm' * 40)

    def test_failure_does_not_merge_and_includes_the_failed_log(self):
        code, result, _ = self.ci('merge', '12', runs={'a' * 40: ['failure']})
        self.assertEqual((code, result['state'], result['merged']), (1, 'failed', False))
        self.assertEqual(result['logs'], {'rust': ['2026-10-25T21:00:01Z error: boom']})
        self.assertFalse(any(call.startswith('pr merge') for call in self.gh_calls))

    def test_a_run_superseded_by_a_push_follows_the_new_head(self):
        code, result, stderr = self.ci('merge', '12', runs={'a' * 40: ['cancelled'], 'b' * 40: ['success']},
                                       heads=('a' * 40, 'b' * 40))
        self.assertEqual((code, result['commit'], result['merged']), (0, 'b' * 40, True))
        self.assertIn('superseded', stderr)

    def test_cancelled_on_the_current_head_is_reported(self):
        code, result, _ = self.ci('merge', '12', runs={'a' * 40: ['cancelled']})
        self.assertEqual((code, result['state'], result['merged']), (3, 'cancelled', False))

    def test_conflicts_are_named(self):
        code, result, _ = self.ci('merge', '12', runs={'a' * 40: ['success']}, merge_exit=1, mergeable='CONFLICTING')
        self.assertEqual((code, result['merged'], result['conflict']), (4, False, True))
        self.assertIn('merge origin/main', result['error'])

    def test_wait_defaults_to_the_merge_tier_on_main(self):
        code, result, stderr = self.ci('wait', runs={'c' * 40: ['running', 'success']})
        self.assertEqual((code, result['workflow'], result['state']), (0, 'merge.yml', 'passed'))
        self.assertIn('api repos/{owner}/{repo}/commits/main -q .sha', self.gh_calls)
        self.assertIn('rust: success in 31s', stderr)

    def test_hooks_warning_names_off_foreign_and_own_hooks(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        import ci
        with tempfile.TemporaryDirectory() as temp:
            env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
            git = lambda *args: subprocess.run(['git', '-C', temp, *args], check=True, env=env, capture_output=True)
            git('init', '-q')
            cwd, saved = os.getcwd(), dict(os.environ)
            os.chdir(temp)
            os.environ.clear()
            os.environ.update(env)  # hooks export GIT_DIR, which would point ci.py at the real repo
            try:
                self.assertIn('hooks are off', ci.hooks_warning())
                git('config', 'core.hooksPath', '/elsewhere/.githooks')
                self.assertIn('not this checkout', ci.hooks_warning())
                git('config', 'core.hooksPath', '.githooks')
                self.assertIsNone(ci.hooks_warning())
            finally:
                os.chdir(cwd)
                os.environ.clear()
                os.environ.update(saved)

    def test_merge_tier_failure_lists_failed_new_and_fixed_phases(self):
        history = [{'databaseId': 7, 'conclusion': 'failure', 'url': 'u7'}, {'databaseId': 6, 'conclusion': 'cancelled', 'url': 'u6'},
                   {'databaseId': 5, 'conclusion': 'failure', 'url': 'u5'}, {'databaseId': 4, 'conclusion': 'failure', 'url': 'u4'}]
        phases = {'7': [['build', False], ['timer-model', True], ['http-native', False], ['tls-native', True]],
                  '4': [['build', False], ['timer-model', False], ['http-native', True]]}
        code, result, _ = self.ci('status', runs={'c' * 40: ['failure']}, history=history, phases=phases)
        self.assertEqual((code, result['failed_phases']), (1, ['build', 'http-native']))
        # Run 6 was cancelled and run 5 has no phases artifact, so run 4 is the comparison.
        self.assertEqual((result['previous_run'], result['new_failures'], result['fixed']), ('u4', ['http-native'], ['timer-model']))
        self.assertEqual(result['logs'], {'rust': ['2026-10-25T21:00:01Z error: boom']})

    def test_runs_without_phases_keep_the_log_tail(self):
        code, result, _ = self.ci('status', runs={'c' * 40: ['failure']})
        self.assertNotIn('failed_phases', result)
        self.assertIn('rust', result['logs'])

    def test_status_without_a_run_is_none(self):
        code, result, _ = self.ci('status', '--commit', 'abc1234', runs={})
        self.assertEqual((code, result['state']), (2, 'none'))


if __name__ == '__main__':
    unittest.main()
