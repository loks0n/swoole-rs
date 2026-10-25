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
import json, sys
args = sys.argv[1:]
if args[0] == 'api':
    print('a' * 40)
elif args[:2] == ['run', 'list']:
    print(json.dumps([{'databaseId': 7, 'status': 'completed', 'conclusion': 'failure', 'url': 'u'}]))
elif args[:2] == ['run', 'view']:
    print(json.dumps({'jobs': [{'name': 'rust', 'status': 'completed', 'conclusion': 'failure',
                                'startedAt': '2026-10-25T21:00:00Z', 'completedAt': '2026-10-25T21:00:31Z'},
                               {'name': 'hybrid', 'status': 'in_progress', 'conclusion': '',
                                'startedAt': '2026-10-25T21:00:00Z', 'completedAt': '0001-01-01T00:00:00Z'}]}))
'''


class Mcp(unittest.TestCase):
    def call(self, *messages):
        with tempfile.TemporaryDirectory() as temp:
            gh = Path(temp) / 'gh'
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': temp + os.pathsep + os.environ['PATH']}
            stdin = ''.join(json.dumps(message) + '\n' for message in messages)
            result = subprocess.run([sys.executable, ROOT / 'tools/mcp.py'], input=stdin, env=env,
                                    capture_output=True, text=True, check=True)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_initialize_list_and_call(self):
        init, listed, called = self.call(
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
             'params': {'name': 'workflow_get', 'arguments': {'workflow': 'pr.yml', 'commit': 'abc1234'}}})
        self.assertEqual(init['result']['capabilities'], {'tools': {}})
        self.assertEqual({tool['name'] for tool in listed['result']['tools']}, {'workflow_get', 'workflow_wait'})
        result = json.loads(called['result']['content'][0]['text'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['jobs'], [{'name': 'rust', 'conclusion': 'failure', 'seconds': 31},
                                          {'name': 'hybrid', 'conclusion': 'in_progress', 'seconds': None}])

    def test_unknown_method_is_an_error(self):
        (reply,) = self.call({'jsonrpc': '2.0', 'id': 1, 'method': 'nope'})
        self.assertEqual(reply['error']['code'], -32601)


if __name__ == '__main__':
    unittest.main()
