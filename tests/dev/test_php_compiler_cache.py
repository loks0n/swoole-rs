"""Exercise real compiler-cache reuse/invalidation without changing source paths."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import build_upstream


class PhpCompilerCache(unittest.TestCase):
    def test_disabled_preserves_compiler_environment(self):
        env = {'CC': 'custom cc', 'CFLAGS': '-O1'}
        self.assertIs(build_upstream.compiler_cache_environment(SimpleNamespace(), env, Path('build.log')), env)
        self.assertIsNone(build_upstream.compiler_cache_identity(SimpleNamespace()))

    @unittest.skipUnless(shutil.which('ccache'), 'explicit ccache executable unavailable')
    def test_concurrent_workers_reuse_shared_objects_with_private_outputs(self):
        with tempfile.TemporaryDirectory(prefix='swr shared cache ') as directory:
            root = Path(directory); source = root/'value.c'
            source.write_text('#include <stdio.h>\nint main(void){printf("%s:31", __FILE__);}')
            workers = [root/'one', root/'two']
            args = SimpleNamespace(ccache=Path(shutil.which('ccache')))
            envs = []
            with patch.dict(os.environ, {'SWOOLE_RS_CACHE_ROOT': str(root/'cache')}):
                for worker in workers:
                    worker.mkdir()
                    with patch.object(build_upstream, 'ROOT', worker):
                        envs.append(build_upstream.compiler_cache_environment(args, os.environ, worker/'build.log'))
            def compile_worker(index):
                worker, env = workers[index], envs[index]
                subprocess.run([*shlex.split(env['CC']), '-c', str(source), '-o', str(worker/'value.o')],
                               cwd=worker, env=env, check=True, capture_output=True)
            compile_worker(0)  # Populate once, then exercise two concurrent readers.
            (workers[0]/'value.o').unlink()
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(compile_worker, range(2)))
            self.assertEqual((workers[0]/'value.o').read_bytes(), (workers[1]/'value.o').read_bytes())
            for worker in workers:
                binary = worker/'value'
                subprocess.run(['cc', str(worker/'value.o'), '-o', str(binary)], check=True, capture_output=True)
                self.assertEqual(subprocess.check_output([str(binary)], text=True), f'{source}:31')
                self.assertIn('preprocessed_cache_hit', (worker/'build.ccache.log').read_text())

    @unittest.skipUnless(shutil.which('ccache'), 'explicit ccache executable unavailable')
    def test_object_eviction_header_and_flag_invalidation_preserve_file_macro(self):
        with tempfile.TemporaryDirectory(prefix='swr compiler cache ') as directory:
            root = Path(directory)
            source, header, obj, binary = [root / name for name in ['value.c', 'value.h', 'value.o', 'value']]
            header.write_text('#define VALUE 17\n')
            source.write_text('#include "value.h"\n#include <stdio.h>\nint main(void) { printf("%s:%d", __FILE__, VALUE + FLAG); }\n')
            args = SimpleNamespace(ccache=Path(shutil.which('ccache')))
            with patch.object(build_upstream, 'ROOT', root):
                # Hostile inherited settings must not suppress flag checking or
                # substitute another cache. Inline safety settings take priority.
                env = build_upstream.compiler_cache_environment(args, {**os.environ,
                    'CCACHE_IGNOREOPTIONS': '-DFLAG=*', 'CCACHE_BASEDIR': str(root),
                    'CCACHE_COMPILER': '/missing-foreign-compiler', 'CCACHE_PREFIX': '/missing-wrapper'}, root / 'build.log')
                for index, value, flag in [(0, 17, 1), (1, 17, 1), (2, 18, 1), (3, 18, 2)]:
                    header.write_text(f'#define VALUE {value}\n')
                    subprocess.run([*shlex.split(env['CC']), f'-DFLAG={flag}', '-c', str(source), '-o', str(obj)],
                                   env=env, check=True, capture_output=True)
                    subprocess.run(['cc', str(obj), '-o', str(binary)], check=True, capture_output=True)
                    self.assertEqual(subprocess.check_output([str(binary)], text=True), f'{source}:{value + flag}')
                    obj.unlink()
                stats = (root / 'build.ccache.log').read_text().splitlines()
                self.assertEqual(stats.count('preprocessed_cache_hit'), 1)
                self.assertEqual(stats.count('cache_miss'), 3)
                identity = build_upstream.compiler_cache_identity(args)
                self.assertEqual(identity['max_size'], '256MiB')
                self.assertFalse(identity['direct_mode'])
                self.assertEqual(identity['base_dir'], '')
                self.assertTrue(Path(identity['cache_dir']).is_dir())
                self.assertNotIn('base_dir=' + str(root), env['CC'])


if __name__ == '__main__':
    unittest.main()
