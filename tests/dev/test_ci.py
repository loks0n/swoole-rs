"""tools/ci.py against a fake gh: run states, failure logs and phases, following replaced runs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
# Runs are scripted per commit in FAKE_RUNS: {sha: [conclusion, ...]}, one entry
# consumed per `run list`.
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
elif args[0] == 'api' and '/compare/' in args[1]:
    print(data.get('compare', 'ahead'))
elif args[0] == 'api':
    print('c' * 40)
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
    def ci(self, *args, runs, **extra):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / 'gh'
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            state, log = Path(temp) / 'state.json', Path(temp) / 'gh.log'
            state.write_text(json.dumps({'runs': runs, **extra}))
            env = {**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH'],
                   'FAKE_STATE': str(state), 'FAKE_GH_LOG': str(log)}
            result = subprocess.run([sys.executable, ROOT / 'tools/ci.py', *args, '--poll', '0', '--json'],
                                    env=env, capture_output=True, text=True)
            self.gh_calls = log.read_text().splitlines() if log.exists() else []
        return result.returncode, json.loads(result.stdout or '{}'), result.stderr

    def test_wait_defaults_to_the_merge_tier_on_main(self):
        code, result, stderr = self.ci('wait', runs={'c' * 40: ['running', 'success']})
        self.assertEqual((code, result['workflow'], result['state']), (0, 'merge.yml', 'passed'))
        self.assertIn('api repos/{owner}/{repo}/commits/main -q .sha', self.gh_calls)
        self.assertIn('rust: success in 31s', stderr)

    def test_wait_follows_the_run_that_replaced_its_commit(self):
        history = [{'headSha': 'd' * 40}]
        code, result, stderr = self.ci('wait', runs={'c' * 40: ['cancelled'], 'd' * 40: ['success']}, history=history)
        self.assertEqual((code, result['commit'], result['state']), (0, 'd' * 40, 'passed'))
        self.assertIn('replaced by the run on ddddddd', stderr)
        code, result, _ = self.ci('wait', runs={'c' * 40: ['cancelled']}, history=history, compare='diverged')
        self.assertEqual((code, result['commit'], result['state']), (3, 'c' * 40, 'cancelled'))

    def test_merge_tier_failure_lists_failed_new_and_fixed_phases(self):
        history = [{'databaseId': 7, 'conclusion': 'failure', 'url': 'u7'}, {'databaseId': 6, 'conclusion': 'cancelled', 'url': 'u6'},
                   {'databaseId': 5, 'conclusion': 'failure', 'url': 'u5'}, {'databaseId': 4, 'conclusion': 'failure', 'url': 'u4'}]
        phases = {'7': [['build', False], ['timer-model', True], ['http-native', False], ['tls-native', True],
                        ['ports-added', False]],
                  '4': [['build', False], ['timer-model', False], ['http-native', True]]}
        code, result, _ = self.ci('status', runs={'c' * 40: ['failure']}, history=history, phases=phases)
        self.assertEqual((code, result['failed_phases']), (1, ['build', 'http-native', 'ports-added']))
        # Run 6 was cancelled and run 5 has no phases artifact, so run 4 is the comparison.
        # ports-added didn't exist in run 4, so its failure is new as well.
        self.assertEqual((result['previous_run'], result['new_failures'], result['fixed']),
                         ('u4', ['http-native', 'ports-added'], ['timer-model']))
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
