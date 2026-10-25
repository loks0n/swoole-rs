"""The repository MCP server speaks stdio JSON-RPC and maps workflow runs to passed/failed/running/none."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FAKE_GH = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['FAKE_GH_LOG'], 'a') as log:
    log.write(' '.join(args) + '\\n')
if args[0] == 'api' or args[:2] == ['pr', 'view']:
    print('a' * 40)
elif args[:2] == ['pr', 'merge']:
    pass
elif args[:2] == ['run', 'list']:
    print(json.dumps([{'databaseId': 7, 'status': 'completed', 'conclusion': os.environ['FAKE_CONCLUSION'], 'url': 'u'}]))
elif args[:2] == ['run', 'view']:
    print(json.dumps({'jobs': [{'name': 'rust', 'status': 'completed', 'conclusion': 'failure',
                                'startedAt': '2026-10-25T21:00:00Z', 'completedAt': '2026-10-25T21:00:31Z'},
                               {'name': 'hybrid', 'status': 'in_progress', 'conclusion': '',
                                'startedAt': '2026-10-25T21:00:00Z', 'completedAt': '0001-01-01T00:00:00Z'}]}))
'''


class Mcp(unittest.TestCase):
    def call(self, *messages, conclusion='failure'):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / 'gh'
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            log = Path(temp) / 'gh.log'
            env = {**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH'],
                   'FAKE_GH_LOG': str(log), 'FAKE_CONCLUSION': conclusion}
            stdin = ''.join(json.dumps(message) + '\n' for message in messages)
            result = subprocess.run([sys.executable, ROOT / 'tools/mcp.py'], input=stdin, env=env,
                                    capture_output=True, text=True, check=True)
            self.gh_calls = log.read_text().splitlines() if log.exists() else []
        return [json.loads(line) for line in result.stdout.splitlines()]

    def merge_when_green(self, conclusion):
        (reply,) = self.call({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                              'params': {'name': 'pr_merge_when_green', 'arguments': {'number': 12}}},
                             conclusion=conclusion)
        return json.loads(reply['result']['content'][0]['text'])

    def test_merges_the_head_that_passed(self):
        self.assertTrue(self.merge_when_green('success')['merged'])
        self.assertIn('pr merge 12 --squash --delete-branch --match-head-commit ' + 'a' * 40, self.gh_calls)

    def test_failed_checks_do_not_merge(self):
        result = self.merge_when_green('failure')
        self.assertEqual((result['state'], result['merged']), ('failed', False))
        self.assertFalse(any(call.startswith('pr merge') for call in self.gh_calls))

    def test_initialize_list_and_call(self):
        init, listed, called = self.call(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'workflow_get', 'arguments': {'workflow': 'pr.yml', 'commit': 'abc1234'}}})
        self.assertEqual(init['result']['capabilities'], {'tools': {}})
        self.assertEqual({tool['name'] for tool in listed['result']['tools']}, {'workflow_get', 'workflow_wait', 'pr_merge_when_green'})
        result = json.loads(called['result']['content'][0]['text'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['jobs'], [{'name': 'rust', 'conclusion': 'failure', 'seconds': 31},
                                          {'name': 'hybrid', 'conclusion': 'in_progress', 'seconds': None}])

    def test_unknown_method_is_an_error(self):
        (reply,) = self.call({'jsonrpc': '2.0', 'id': 1, 'method': 'nope'})
        self.assertEqual(reply['error']['code'], -32601)


if __name__ == '__main__':
    unittest.main()
