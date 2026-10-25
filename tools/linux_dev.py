#!/usr/bin/env python3
"""Run local commands in a reusable Linux toolchain, with a private persistent checkout."""
import argparse
import hashlib
import shutil
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT, run_isolated
from tools.harness import exclusive
from tools.private_copy import copy_private



def sync_source(source, target):
    """Sync private inputs on the host so APFS can clone their physical storage."""
    excluded = {'target', '.git', '__pycache__', '.venv', 'node_modules'}
    if target.exists() and not target.is_dir():
        target.unlink()
    target.mkdir(parents=True, exist_ok=True)
    for old in target.iterdir():
        if old.name not in excluded and not (source / old.name).exists():
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    for path in source.iterdir():
        if path.name in excluded or path.is_symlink():
            continue
        out = target / path.name
        if path.is_dir():
            sync_source(path, out)
        else:
            if out.is_dir():
                shutil.rmtree(out)
            if not out.exists() or out.read_bytes() != path.read_bytes():
                copy_private(path, out)


def source_snapshot(source):
    """Pin the exact commit and immutable object store, without sharing refs/index."""
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--verify', 'HEAD^{commit}'], text=True).strip()
    common = Path(subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--path-format=absolute',
                                         '--git-common-dir'], text=True).strip())
    objects = (common / 'objects').resolve()
    alternates = objects / 'info/alternates'
    if alternates.exists() and alternates.read_text().strip():
        raise ValueError('Source object store has external alternates; mount its dependencies explicitly before sharing')
    return head, objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild-image', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    dockerfile = ROOT / 'tools/Dockerfile.dev'
    tag = 'swoole-rs-dev:' + hashlib.sha256(dockerfile.read_bytes()).hexdigest()[:16]
    try:
        ready = run_isolated(['docker', 'version', '--format', '{{.Server.Version}}'], timeout=30)
    except subprocess.TimeoutExpired:
        parser.exit(1, 'Docker control readiness timed out; no rebuild or workspace sync started.\n')
    if ready.returncode:
        parser.exit(1, 'Docker control unavailable; no rebuild or workspace sync started.\n')
    missing_image = False
    if not args.rebuild_image:
        try:
            missing_image = subprocess.run(['docker', 'image', 'inspect', tag], timeout=30,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
        except subprocess.TimeoutExpired:
            parser.exit(1, 'Docker image inspection timed out; no rebuild or workspace sync started. Check the local Docker service.\n')
    if args.rebuild_image or missing_image:
        subprocess.run(['docker', 'build', *(['--pull', '--no-cache'] if args.rebuild_image else []),
                        '-t', tag, '-f', str(dockerfile), str(ROOT / 'tools')], check=True)
    workspace = ROOT / 'target/linux-dev'
    workspace.mkdir(parents=True, exist_ok=True)
    # Copy only repository inputs, including deletions; never copy host build outputs.
    sync = r'''import os, subprocess
from pathlib import Path
target = Path('/work')
subprocess.run(['git', 'init', '-q', str(target)], check=True)
objects = Path(os.environ['SWOOLE_RS_SOURCE_OBJECTS'])
alternates = target / '.git/objects/info/alternates'
expected = str(objects) + '\n'
if alternates.exists() and alternates.read_text() != expected:
    raise ValueError('Private workspace already uses a different object store; preserve it until explicitly migrated')
alternates.parent.mkdir(parents=True, exist_ok=True)
alternates.write_text(expected)
revision = os.environ['SWOOLE_RS_SOURCE_COMMIT']
subprocess.run(['git', '-C', str(target), 'cat-file', '-e', revision + '^{commit}'], check=True)
subprocess.run(['git', '-C', str(target), 'reset', '--mixed', '-q', revision], check=True)
'''
    shared = ROOT / 'target/linux-cache'
    shared.mkdir(parents=True, exist_ok=True)
    mounts = ['--mount', f'type=bind,source={shared},target=/shared-cache',
              '--mount', f'type=bind,source={ROOT},target=/repo,readonly',
              '--mount', f'type=bind,source={workspace},target=/work']
    command = args.command
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        command = ['php', '--version']
    # One container owns sync and execution. exec preserves signals and exit status.
    launcher = 'import os,sys; exec(sys.argv[1]); os.execvp(sys.argv[2], sys.argv[2:])'
    with exclusive(workspace.with_suffix('.lock')):
        (workspace / 'target/tmp').mkdir(parents=True, exist_ok=True)
        # Mount only immutable objects at the same absolute path on both hosts.
        # The private refs/index remain private; exact commit verification precedes reset.
        revision, objects = source_snapshot(ROOT)
        sync_source(ROOT, workspace)
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != revision:
            raise ValueError('Source HEAD changed during Linux snapshot preparation')
        print(f'Linux source {revision}: shared read-only Git objects', file=sys.stderr)
        return subprocess.run(['docker', 'run', '--rm', '--init', *mounts,
                               '--mount', f'type=bind,source={objects},target={objects},readonly',
                               '--env', 'SWOOLE_RS_SOURCE_OBJECTS=' + str(objects),
                               '--env', 'SWOOLE_RS_SOURCE_COMMIT=' + revision,
                               '--env', 'TMPDIR=/work/target/tmp',
                               '--env', 'GIT_CEILING_DIRECTORIES=/work/target',
                               '--env', 'CARGO_HOME=/shared-cache/cargo-linux',
                               '--env', 'CCACHE_DIR=/shared-cache/ccache',
                               '--env', 'CCACHE_MAXSIZE=256MiB', tag,
                               'python3', '-c', launcher, sync, *command]).returncode


if __name__ == '__main__':
    sys.exit(main())
