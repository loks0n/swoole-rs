#!/usr/bin/env python3
"""Complete pinned HTTP2 PHPT manifest; no runtime or parity claim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN


def inventory(source):
    readiness = json.loads(Path(__file__).with_name('inventory.json').read_text())
    if readiness['upstream_commit'] != PIN:
        raise ValueError('Readiness and source pins differ')
    candidates = readiness['phpt']
    if len({row['path'] for row in candidates}) != len(candidates):
        raise ValueError('Duplicate original PHPT paths')
    tests = []
    for row in sorted(candidates, key=lambda row: row['path']):
        content = subprocess.check_output(['git', '-C', str(source), 'show', f'{PIN}:{row["path"]}'])
        if hashlib.sha256(content).hexdigest() != row['sha256']:
            raise ValueError('Original test identity changed: ' + row['path'])
        tests.append({'path': row['path'], 'sha256': row['sha256'],
                      'module': 'http2', 'requires': ['upstream_test_bootstrap']})
    # Reuse the integrated full original support inventory instead of maintaining
    # another partial set of bootstrap/example/logo/fuzz fixtures. No HTTP tests
    # are imported or selected here, only pinned support blob identities.
    helper_path = ROOT/'tests/modules/http/full_originals.py'
    spec = importlib.util.spec_from_file_location('http2_original_support', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    support_manifest = helper.inventory(source)
    if support_manifest['commit'] != PIN:
        raise ValueError('Support and test pins differ')
    support = support_manifest['support_files']
    return {'repository': 'https://github.com/swoole/swoole-src', 'commit': PIN,
            'tests': tests, 'support_files': support,
            'inventory': {'cases': len(tests), 'support_blobs': len(support),
                          'denominators': readiness['denominators'],
                          'native_declarations': len(readiness['native']),
                          'selection': 'Every original PHPT from the pinned F05 readiness inventory; no exclusions',
                          'execution_status': 'not_run',
                          'requirements': 'Native/PHP feature probes and original SKIPIF/assertions remain untouched. Missing optional packages/services may fail or skip; never inferred passed.'}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = inventory(a.source)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest['inventory']))


if __name__ == '__main__':
    main()
