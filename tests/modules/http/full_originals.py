#!/usr/bin/env python3
"""Generate the complete pinned HTTP PHPT inventory for the official runner.

This does not run tests or modify their assertions/probes. External dependencies
absent from the documented local support adapter remain explicit unsupported rows.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
SUPPORT_ROOTS = ['tests/include', 'examples',
         'docs/swoole-logo.svg', 'core-tests/fuzz/cases', 'README.md']
EXTERNAL = {'bug_2444.phpt': 'external_mysql_service',
            'tmp-content-type.phpt': 'composer_guzzle'}


def inventory(source, group="swoole_http_server"):
    test_root = "tests/" + group
    external = EXTERNAL if group == "swoole_http_server" else {"close_socket.phpt": "external_baidu_https"}
    command = ['git', '-C', str(source)]
    rows = subprocess.check_output([*command, 'ls-tree', '-r', PIN, '--', test_root, *SUPPORT_ROOTS], text=True)
    entries = [row.split('\t', 1)[1] for row in rows.splitlines() if row.split()[1] == 'blob']
    queries = ''.join(f'{PIN}:{path}\n' for path in entries).encode()
    batch = subprocess.run([*command, 'cat-file', '--batch'], input=queries,
                           stdout=subprocess.PIPE, check=True).stdout
    hashes = {}
    offset = 0
    total_bytes = 0
    for path in entries:
        end = batch.index(b'\n', offset)
        _oid, kind, size = batch[offset:end].split()
        if kind != b'blob':
            raise ValueError(f'Not a pinned blob: {path}')
        size = int(size)
        data = batch[end + 1:end + 1 + size]
        if len(data) != size or batch[end + 1 + size:end + 2 + size] != b'\n':
            raise ValueError(f'Truncated pinned blob: {path}')
        hashes[path] = hashlib.sha256(data).hexdigest()
        offset = end + 2 + size
        total_bytes += size
    tests = []
    support = []
    for path, digest in hashes.items():
        item = {'path': path, 'sha256': digest}
        if path.startswith(test_root + '/') and path.endswith('.phpt'):
            requirements = ['upstream_test_bootstrap', 'http', 'processes', 'php_sockets']
            if group == 'swoole_http_server_coro':
                requirements.append('coroutines')
            if Path(path).name in external:
                requirements.append(external[Path(path).name])
            tests.append({**item, 'module': 'http', 'requires': requirements})
        else:
            support.append(item)
    tree = subprocess.check_output([*command, 'rev-parse', f'{PIN}:{test_root}'], text=True).strip()
    return {'repository': 'https://github.com/swoole/swoole-src', 'tag': 'v6.2.2',
            'commit': PIN, 'http_tree': tree, 'tests': tests, 'support_files': support,
            'inventory': {'cases': len(tests), 'support_blobs': len(support),
                          'total_pinned_bytes': total_bytes,
                          'external_dependencies': external,
                          'selection': 'Every PHPT in the complete pinned ' + group + ' tree; no exclusions'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--group', choices=['swoole_http_server', 'swoole_http_server_coro'], default='swoole_http_server')
    args = parser.parse_args()
    manifest = inventory(args.source, args.group)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['inventory']))


if __name__ == '__main__':
    main()
