#!/usr/bin/env python3
"""Edit a module's upstream patches as a Git branch: one commit per patch file.

  patches.py checkout MODULE   clone the pin to target/patches/MODULE and commit each patch
  patches.py export MODULE     write each commit back to migration/patches/MODULE
  patches.py rehash OLD [NEW]  rewrite recorded hashes of upstream files changed from OLD to NEW (default: the pin)
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_upstream import COMMIT, VERSION
from tools.harness import ROOT


def git(work, *args):
    return subprocess.run(['git', '-C', str(work), '-c', 'user.name=patches', '-c', 'user.email=patches@localhost', *args],
                          check=True, capture_output=True, text=True).stdout


def checkout(module, patches, work):
    if work.exists():
        raise SystemExit(f'{work} exists; export or delete it first')
    reference = ROOT / 'target/upstream/src'
    source = [str(reference)] if (reference / '.git').exists() else ['--depth', '1', '--branch', VERSION,
                                                                     'https://github.com/swoole/swoole-src.git']
    subprocess.run(['git', '-c', 'advice.detachedHead=false', 'clone', '-q', *source, str(work)], check=True)
    git(work, 'checkout', '-q', '-b', 'patches/' + module, COMMIT)
    baseline = {}
    for patch in json.loads((patches / 'manifest.json').read_text())['patches']:
        git(work, 'apply', '--index', str(patches / patch['path']))
        git(work, 'commit', '-q', '-m', patch['path'])
        baseline[patch['path']] = git(work, 'diff', '-U1', 'HEAD~', 'HEAD')
    (work / '.git/patches-baseline.json').write_text(json.dumps(baseline))
    print(work)


def export(patches, work):
    # A commit whose diff is unchanged since checkout keeps its patch file byte for byte, so
    # frozen and generator-written patches survive a round trip.
    baseline = json.loads((work / '.git/patches-baseline.json').read_text())
    manifest = json.loads((patches / 'manifest.json').read_text())
    previous = {row['path']: row for row in manifest['patches']}
    rows = []
    for commit in git(work, 'rev-list', '--reverse', COMMIT + '..HEAD').split():
        name = git(work, 'log', '-1', '--format=%s', commit).strip()
        # One context line, so patches from different modules to neighbouring lines still stack.
        body = git(work, 'diff', '-U1', commit + '~', commit)
        if name in previous and baseline.get(name) == body:
            rows.append(previous[name])
            continue
        (patches / name).write_text(body)
        rows.append({'path': name, 'sha256': hashlib.sha256(body.encode()).hexdigest(),
                     'upstream_paths': git(work, 'diff', '--name-only', commit + '~', commit).split()})
    for stale in set(patches.glob('*.patch')) - {patches / row['path'] for row in rows}:
        stale.unlink()
    updated = {**manifest, 'upstream_commit': COMMIT, 'patches': rows}
    if updated != manifest:
        (patches / 'manifest.json').write_text(json.dumps(updated, indent=2) + '\n')


def rehash(old, new):
    """Rewrite each recorded sha256 or git blob id of an upstream file from its OLD to its NEW value."""
    work = ROOT / 'target/patches/.rehash'
    shutil.rmtree(work, ignore_errors=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    git(work, 'fetch', '-q', '--depth', '1', 'https://github.com/swoole/swoole-src.git', old, new)
    blob = lambda commit, path: hashlib.sha256(subprocess.run(['git', '-C', str(work), 'show', f'{commit}:{path}'],
                                                              check=True, capture_output=True).stdout).hexdigest()
    status = git(work, 'diff', '--name-status', '--no-renames', old, new).splitlines()
    mapping = {}
    for kind, path in (line.split('\t', 1) for line in status):
        if kind == 'M':
            mapping[blob(old, path)] = blob(new, path)
            mapping[git(work, 'rev-parse', f'{old}:{path}').strip()] = git(work, 'rev-parse', f'{new}:{path}').strip()
        elif kind == 'D':
            print(f'deleted upstream, review any reference: {path}')
    pattern = re.compile('|'.join(map(re.escape, mapping)))
    for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT, text=True).split('\0'):
        path = ROOT / name
        if not name or name.startswith('migration/patches/') or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        updated = pattern.sub(lambda match: mapping[match.group()], text)
        if updated != text:
            path.write_text(updated)
            print(name)
    shutil.rmtree(work)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['checkout', 'export', 'rehash'])
    parser.add_argument('module', help='module, or OLD commit for rehash')
    parser.add_argument('new', nargs='?', default=COMMIT, help='rehash only: NEW commit')
    args = parser.parse_args()
    if args.command == 'rehash':
        return rehash(args.module, args.new)
    patches, work = ROOT / 'migration/patches' / args.module, ROOT / 'target/patches' / args.module
    if not patches.is_dir():
        raise SystemExit(f'No patch directory: {patches}')
    checkout(args.module, patches, work) if args.command == 'checkout' else export(patches, work)


if __name__ == '__main__':
    main()
