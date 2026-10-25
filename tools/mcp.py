#!/usr/bin/env python3
"""Stdio MCP server for agents working on this repository.

Tools shell out to the GitHub CLI, so an agent needs only `gh` and GH_TOKEN.
"""
import json
import subprocess
import sys
import time

WORKFLOW = {'type': 'string', 'description': 'Workflow file in .github/workflows, e.g. pr.yml'}
COMMIT = {'type': 'string', 'description': 'Commit sha (7+ characters) or branch; default main'}
TOOLS = [
    {'name': 'workflow_get', 'description': "A workflow's run on a commit: passed, failed, running or none, with job durations.",
     'inputSchema': {'type': 'object', 'properties': {'workflow': WORKFLOW, 'commit': COMMIT}, 'required': ['workflow']}},
    {'name': 'workflow_wait', 'description': 'Wait for a workflow run on a commit to finish, then answer as workflow_get. '
                                             'Gives up with none if no run appears within 5 minutes.',
     'inputSchema': {'type': 'object', 'properties': {
         'workflow': WORKFLOW, 'commit': COMMIT,
         'timeout_s': {'type': 'integer', 'minimum': 0, 'maximum': 3600, 'description': 'Default 1800'}},
         'required': ['workflow']}},
]


def gh(*args):
    return subprocess.run(['gh', *args], capture_output=True, text=True, check=True).stdout


def resolve(commit):
    return gh('api', 'repos/{owner}/{repo}/commits/' + (commit or 'main'), '-q', '.sha').strip()


def workflow_get(workflow, commit=None, sha=None):
    sha = sha or resolve(commit)
    runs = json.loads(gh('run', 'list', '--workflow', workflow, '--commit', sha, '--limit', '1',
                         '--json', 'databaseId,status,conclusion,url'))
    if not runs:
        return {'commit': sha, 'state': 'none'}
    run = runs[0]
    state = ('running' if run['status'] != 'completed'
             else 'passed' if run['conclusion'] == 'success' else 'failed')
    jobs = json.loads(gh('run', 'view', str(run['databaseId']), '--json', 'jobs'))['jobs']
    return {'commit': sha, 'state': state, 'conclusion': run['conclusion'], 'url': run['url'],
            'jobs': [{'name': job['name'], 'conclusion': job['conclusion'] or job['status'],
                      'seconds': duration(job)} for job in jobs]}


def duration(job):
    if not job.get('startedAt') or not job.get('completedAt'):
        return None
    parse = lambda value: time.mktime(time.strptime(value, '%Y-%m-%dT%H:%M:%SZ'))
    return int(parse(job['completedAt']) - parse(job['startedAt']))


def workflow_wait(workflow, commit=None, timeout_s=1800, poll=10):
    sha = resolve(commit)
    deadline, appear_by = time.monotonic() + timeout_s, time.monotonic() + 300
    while True:
        result = workflow_get(workflow, sha=sha)
        if result['state'] in ('passed', 'failed'):
            return result
        if result['state'] == 'none' and time.monotonic() > appear_by:
            return result
        if time.monotonic() > deadline:
            return {**result, 'timed_out': True}
        time.sleep(poll)


HANDLERS = {'workflow_get': workflow_get, 'workflow_wait': workflow_wait}


def handle(message):
    method, params = message.get('method'), message.get('params') or {}
    if method == 'initialize':
        return {'protocolVersion': params.get('protocolVersion', '2025-06-18'),
                'capabilities': {'tools': {}}, 'serverInfo': {'name': 'swoole-rs', 'version': '1'}}
    if method == 'tools/list':
        return {'tools': TOOLS}
    if method == 'tools/call':
        try:
            text, error = json.dumps(HANDLERS[params['name']](**params.get('arguments', {}))), False
        except subprocess.CalledProcessError as failure:
            text, error = failure.stderr.strip() or str(failure), True
        except (KeyError, TypeError) as failure:
            text, error = f'Invalid tool call: {failure}', True
        return {'content': [{'type': 'text', 'text': text}], 'isError': error}
    if method == 'ping':
        return {}
    raise LookupError(method)


def main():
    for line in sys.stdin:
        message = json.loads(line)
        if 'id' not in message:
            continue  # notifications need no reply
        try:
            reply = {'jsonrpc': '2.0', 'id': message['id'], 'result': handle(message)}
        except LookupError as missing:
            reply = {'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': f'Unknown method {missing}'}}
        print(json.dumps(reply), flush=True)


if __name__ == '__main__':
    main()
