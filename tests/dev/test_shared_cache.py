"""Worktrees share cache storage without sharing mutable build artifacts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import shared_cache, build_upstream, linux_dev


class SharedCaches(unittest.TestCase):
    def test_private_source_sync_preserves_targets_and_independent_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'source', Path(directory)/'private'
            source.mkdir(); target.mkdir()
            (source/'nested').mkdir(); (source/'nested/input').write_text('first')
            (target/'target').mkdir(); (target/'target/keep').write_text('private build')
            (target/'.git').mkdir(); (target/'.git/keep').write_text('private refs')
            (target/'removed').write_text('old input')
            linux_dev.sync_source(source, target)
            self.assertFalse((target/'removed').exists())
            self.assertNotEqual((source/'nested/input').stat().st_ino,
                                (target/'nested/input').stat().st_ino)
            (target/'nested/input').write_text('private edit')
            self.assertEqual((source/'nested/input').read_text(), 'first')
            (source/'nested/input').write_text('second')
            linux_dev.sync_source(source, target)
            self.assertEqual((target/'nested/input').read_text(), 'second')
            self.assertEqual((target/'target/keep').read_text(), 'private build')
            self.assertEqual((target/'.git/keep').read_text(), 'private refs')

    def test_two_real_git_worktrees_resolve_one_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SWOOLE_RS_CACHE_ROOT': ''}):
            root = Path(directory) / 'repo'; root.mkdir()
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit', '--allow-empty', '-qm', 'fixture'], check=True)
            second = Path(directory) / 'worker'
            subprocess.run(['git', '-C', str(root), 'worktree', 'add', '--detach', '-q', str(second)], check=True)
            self.assertEqual(shared_cache.cache_root(root), shared_cache.cache_root(second))
            self.assertEqual(shared_cache.compiler_settings(root), shared_cache.compiler_settings(second))
            for cwd in [root, second]:
                with patch.dict(os.environ, {'CARGO_TARGET_DIR': str(cwd/'private-output')}):
                    env = shared_cache.environment(cwd)
                self.assertEqual(env['CARGO_TARGET_DIR'], str(cwd/'private-output'))
                self.assertEqual(env['CCACHE_MAXSIZE'], '256MiB')

    def test_platform_partition_and_explicit_container_mount(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SWOOLE_RS_CACHE_ROOT': directory}):
            with patch.object(shared_cache.sys, 'platform', 'linux'), patch.object(shared_cache.platform, 'machine', return_value='aarch64'):
                settings = shared_cache.compiler_settings()
                self.assertEqual(Path(settings['cache_dir']), Path(directory).resolve()/'ccache/linux-aarch64')
                self.assertEqual(shared_cache.environment()['CARGO_HOME'], str(Path(directory).resolve()/'cargo-linux'))
            with patch.object(shared_cache.sys, 'platform', 'darwin'):
                self.assertEqual(shared_cache.environment()['CARGO_HOME'], str(Path.home()/'.cargo'))
            self.assertFalse(settings['hard_link'])
            self.assertFalse(settings['direct_mode'])
            self.assertEqual(settings['compiler_check'], 'content')
            with patch.dict(os.environ, {'SWOOLE_RS_CACHE_ROOT': 'relative/cache'}):
                with self.assertRaisesRegex(ValueError, 'absolute'):
                    shared_cache.cache_root()

    def test_unavailable_docker_never_rebuilds_or_syncs_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'tools').mkdir()
            (root/'tools/Dockerfile.dev').write_text('fixture')
            with patch.object(linux_dev, 'ROOT', root), \
                 patch.object(linux_dev, 'run_isolated', return_value=subprocess.CompletedProcess('docker', 1)) as run, \
                 patch.object(linux_dev.subprocess, 'run') as downstream, \
                 patch.object(linux_dev, 'sync_source') as sync, \
                 patch('sys.argv', ['linux_dev.py', '--', 'true']):
                with self.assertRaises(SystemExit) as result:
                    linux_dev.main()
                self.assertEqual(result.exception.code, 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0], ['docker', 'version', '--format', '{{.Server.Version}}'])
                sync.assert_not_called()
                downstream.assert_not_called()

    def test_unresponsive_docker_never_rebuilds_or_syncs_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'tools').mkdir()
            (root/'tools/Dockerfile.dev').write_text('fixture')
            with patch.object(linux_dev, 'ROOT', root), \
                 patch.object(linux_dev, 'run_isolated', side_effect=subprocess.TimeoutExpired('docker', 30)) as run, \
                 patch.object(linux_dev.subprocess, 'run') as downstream, \
                 patch.object(linux_dev, 'sync_source') as sync, \
                 patch('sys.argv', ['linux_dev.py', '--', 'true']):
                with self.assertRaises(SystemExit) as result:
                    linux_dev.main()
                self.assertEqual(result.exception.code, 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.kwargs['timeout'], 30)
                sync.assert_not_called()
                downstream.assert_not_called()

    def test_linux_runner_binds_shared_cache_but_keeps_private_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'tools').mkdir(); (root/'tools/Dockerfile.dev').write_text('fixture')
            cache = root/'shared'; calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)
            with patch.object(linux_dev, 'ROOT', root), patch.object(linux_dev, 'cache_root', return_value=cache), \
                 patch.object(linux_dev.subprocess, 'run', side_effect=run), \
                 patch.object(linux_dev, 'run_isolated', side_effect=run), \
                 patch.object(linux_dev, 'source_snapshot', return_value=('a' * 40, root/'objects')), \
                 patch.object(linux_dev, 'sync_source'), \
                 patch.object(linux_dev.subprocess, 'check_output', return_value='a' * 40), \
                 patch('sys.argv', ['linux_dev.py', '--', 'cargo', 'test']):
                self.assertEqual(linux_dev.main(), 0)
            command = next(c for c in calls if c[:2] == ['docker', 'run'])
            self.assertIn(f'type=bind,source={cache},target=/shared-cache', command)
            self.assertIn(f'type=bind,source={root}/target/linux-dev,target=/work', command)
            self.assertIn('SWOOLE_RS_SOURCE_COMMIT=' + 'a' * 40, command)
            self.assertIn(f'type=bind,source={root}/objects,target={root}/objects,readonly', command)
            self.assertNotIn('/source.bundle', str(command))
            compile(command[command.index('-c') + 2], '<container-source-sync>', 'exec')
            self.assertIn('CARGO_HOME=/shared-cache/cargo-linux', command)
            self.assertIn('SWOOLE_RS_CACHE_ROOT=/shared-cache', command)
            self.assertIn('TMPDIR=/work/target/tmp', command)
            self.assertIn('GIT_CEILING_DIRECTORIES=/work/target', command)
            self.assertTrue((root/'target/linux-dev/target/tmp').is_dir())
            self.assertNotIn('CARGO_HOME=/work/target/cargo-home', command)

    def test_bound_temporary_patch_tree_does_not_discover_parent_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'work'
            stage = root / 'target/tmp/disposable'
            stage.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = stage / 'sample.txt'
            source.write_text('before\n')
            overlay = 'diff --git a/sample.txt b/sample.txt\n--- a/sample.txt\n+++ b/sample.txt\n@@ -1 +1 @@\n-before\n+after\n'
            env = {**os.environ, 'GIT_CEILING_DIRECTORIES': str(root / 'target')}
            subprocess.run(['git', 'apply', '-'], input=overlay, text=True, cwd=stage, env=env, check=True)
            self.assertEqual(source.read_text(), 'after\n')
            # Genuine repositories inside target and the main workspace still work.
            child = root / 'target/private-source'
            subprocess.run(['git', 'init', '-q', str(child)], check=True, env=env)
            for repository in (root, child):
                observed = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', '--show-toplevel'], env=env, text=True)
                self.assertEqual(Path(observed.strip()).resolve(), repository.resolve())
