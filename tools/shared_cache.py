#!/usr/bin/env python3
"""Shared download/compiler storage; mutable build outputs remain per worktree."""
import json
import os
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT


def cache_root(root=ROOT):
    override = os.environ.get('SWOOLE_RS_CACHE_ROOT')
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError('SWOOLE_RS_CACHE_ROOT must be absolute')
        return path.resolve()
    git = root / '.git'
    if git.is_file():
        marker = git.read_text().strip()
        if not marker.startswith('gitdir: '):
            raise ValueError('Invalid Git worktree marker: ' + str(git))
        git = (root / marker[8:]).resolve()
    common = git / 'commondir'
    if common.is_file():
        git = (git / common.read_text().strip()).resolve()
    repository = git.resolve().parent if git.is_dir() else root
    return repository / 'target/shared-cache'


def compiler_settings(root=ROOT):
    return dict(cache_dir=str(cache_root(root) / 'ccache' / (sys.platform + '-' + platform.machine())),
                max_size='256MiB', compiler_check='content', direct_mode=False, sloppiness='',
                base_dir='', hash_dir=True, ignore_options='', depend_mode=False,
                compiler='', compiler_type='auto', prefix_command='', prefix_command_cpp='', hard_link=False)


def compiler_launcher(executable, settings, inherited=None):
    # Environment settings work with Debian's ccache4.7 and newer host versions.
    names = dict(cache_dir='DIR', max_size='MAXSIZE', compiler_check='COMPILERCHECK',
                 direct_mode='DIRECT', sloppiness='SLOPPINESS', base_dir='BASEDIR',
                 hash_dir='HASHDIR', ignore_options='IGNOREOPTIONS', depend_mode='DEPEND',
                 compiler='COMPILER', compiler_type='COMPILERTYPE', prefix_command='PREFIX',
                 prefix_command_cpp='PREFIX_CPP', hard_link='HARDLINK', stats_log='STATSLOG')
    inherited = os.environ if inherited is None else inherited
    command = ['env', *[argument for key in inherited if key.startswith('CCACHE_') for argument in ['-u', key]]]
    for key, value in settings.items():
        variable = names[key]
        if isinstance(value, bool):
            variable = ('' if value else 'NO') + variable
            value = 'true'
        command.append('CCACHE_' + variable + '=' + str(value))
    return [*command, str(executable)]


def environment(root=ROOT):
    env = os.environ.copy()
    shared = cache_root(root)
    env['SWOOLE_RS_CACHE_ROOT'] = str(shared)
    env['CARGO_HOME'] = str(shared / 'cargo-linux' if sys.platform.startswith('linux') else Path.home() / '.cargo')
    env['CCACHE_DIR'] = compiler_settings(root)['cache_dir']
    env['CCACHE_MAXSIZE'] = '256MiB'
    return env


def main():
    command = sys.argv[1:]
    if command[:1] == ['--']:
        command = command[1:]
    env = environment()
    if not command:
        print(json.dumps({key: env[key] for key in ['SWOOLE_RS_CACHE_ROOT', 'CARGO_HOME', 'CCACHE_DIR', 'CCACHE_MAXSIZE']}, indent=2))
        return 0
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    sys.exit(main())
