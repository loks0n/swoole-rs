"""Inert compiler fixtures for dependency omissions; no module profiles execute."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools import dev_cache


class NativeCacheInputs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cache-input-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root_patch = patch.object(dev_cache, 'ROOT', self.root)
        self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        self.env_patch = patch.dict(os.environ, {'SWOOLE_RS_NO_CACHE': '0'})
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        self.source = self.root / 'main.c'
        self.source.write_text('int value(void); int main(void){return value();}\n')
        self.output = self.root / 'main'

    def guard(self):
        self.assertGreaterEqual(shutil.disk_usage(self.root).free, 4294967296, 'Unchanged 4GiB guard')

    def object(self, number, suffix='.o'):
        self.guard()
        source, obj = self.root / 'value.c', self.root / ('value' + suffix)
        source.write_text(f'int value(void){{return {number};}}\n')
        subprocess.run(['cc', '-c', str(source), '-o', str(obj)], check=True, capture_output=True, timeout=30)
        return obj

    def compile(self, inputs):
        self.guard()
        result = dev_cache.compile_cached(['cc', str(self.source), *map(str, inputs), '-o', str(self.output)],
                                          output=self.output, scratch=self.root)
        self.assertEqual(result['returncode'], 0, result)
        return result, subprocess.run([str(self.output)], timeout=10).returncode

    def test_object_content_mutation_and_unchanged_hits(self):
        for suffix in ['.o', '.obj']:
            with self.subTest(suffix=suffix):
                for number, hit in [(11, False), (11, True), (12, False), (12, True)]:
                    result, actual = self.compile([self.object(number, suffix)])
                    self.assertEqual(actual, number)
                    self.assertEqual(result['cache_hit'], hit, result)
                cached = self.root / 'target/cache/native' / result['cache_key'] / 'binary'
                self.assertNotEqual(cached.stat().st_ino, self.output.stat().st_ino)

    def test_response_inputs_bypass_reuse(self):
        response = self.root / 'objects.rsp'
        for number in [11, 11, 12]:
            response.write_text(str(self.object(number)) + '\n')
            result, actual = self.compile(['@' + str(response)])
            self.assertEqual(actual, number)
            self.assertFalse(result['cache_hit'])
            self.assertIsNone(result['cache_key'])
            self.assertIn('untracked', result['cache_reason'])

    @unittest.skipUnless(sys.platform == 'darwin', 'Mach-O linker filelist fixture')
    def test_linker_filelist_bypasses_reuse(self):
        filelist = self.root / 'objects.list'
        for number in [11, 11, 12]:
            filelist.write_text(str(self.object(number)) + '\n')
            result, actual = self.compile(['-Wl,-filelist,' + str(filelist)])
            self.assertEqual(actual, number)
            self.assertFalse(result['cache_hit'])
            self.assertIsNone(result['cache_key'])

    def test_searched_static_library_bypasses_reuse(self):
        archive = self.root / 'libvalue.a'
        for number in [11, 11, 12]:
            subprocess.run(['ar', 'rcs', str(archive), str(self.object(number))], check=True,
                           capture_output=True, timeout=30)
            result, actual = self.compile(['-L' + str(self.root), '-lvalue'])
            self.assertEqual(actual, number)
            self.assertFalse(result['cache_hit'])
            self.assertIsNone(result['cache_key'])

    def test_source_file_macro_keeps_original_paths(self):
        for name, hit in [('one', False), ('two', False), ('two', True)]:
            tree = self.root / name; tree.mkdir(exist_ok=True)
            source, output = tree / 'source.c', tree / 'main'
            source.write_text('#include <stdio.h>\nint main(void){puts(__FILE__);}\n')
            self.guard()
            result = dev_cache.compile_cached(['cc', str(source), '-o', str(output)], output=output, scratch=tree)
            self.assertEqual(result['returncode'], 0, result)
            self.assertEqual(result['cache_hit'], hit, result)
            self.assertEqual(subprocess.check_output([str(output)], text=True, timeout=10).strip(), str(source))

    def test_relative_source_debug_directory_tracks_actual_cwd(self):
        output = self.root / 'shared.o'
        original = Path.cwd()
        self.addCleanup(os.chdir, original)
        for name, hit in [('one', False), ('two', False), ('two', True)]:
            tree = (self.root / name).resolve()
            tree.mkdir(exist_ok=True)
            (tree / 'source.c').write_text('int value(void){return 7;}\n')
            os.chdir(tree)
            self.guard()
            result = dev_cache.compile_cached(
                ['cc', '-g', '-c', 'source.c', '-o', str(output)],
                output=output, scratch=self.root)
            self.assertEqual(result['returncode'], 0, result)
            # Same relative argv and source bytes, but DW_AT_comp_dir must name
            # this compilation directory, including after a real cache hit.
            self.assertIn(os.fsencode(tree), output.read_bytes())
            self.assertEqual(result['cache_hit'], hit, result)

    def test_volatile_builtin_and_token_pasted_timestamp_bypass(self):
        for expression in ['__DATE__ " " __TIME__', 'JOIN(__TIME,STAMP__)']:
            self.source.write_text('#include <stdio.h>\n#define JOIN(a,b) a ## b\n'
                                   'int main(void){puts(' + expression + ');}\n')
            values = []
            for epoch in [1700000000, 1700100000]:
                os.utime(self.source, (epoch, epoch))
                with patch.dict(os.environ, {'SOURCE_DATE_EPOCH': str(epoch)}):
                    self.guard()
                    result = dev_cache.compile_cached(['cc', '-w', str(self.source), '-o', str(self.output)],
                                                      output=self.output, scratch=self.root)
                self.assertEqual(result['returncode'], 0, result)
                self.assertFalse(result['cache_hit'])
                self.assertIsNone(result['cache_key'])
                self.assertIn('volatile builtin', result['cache_reason'])
                values.append(subprocess.check_output([str(self.output)], text=True, timeout=10))
            self.assertNotEqual(*values)

    def test_volatile_diagnostic_is_not_silently_reused(self):
        self.source.write_text('#pragma message(__TIME__)\nint main(void){return 0;}\n')
        for _ in range(2):
            result, actual = self.compile([])
            self.assertEqual(actual, 0)
            self.assertIsNone(result['cache_key'])
            self.assertFalse(result['cache_hit'])
            self.assertIn('volatile builtin', result['cache_reason'])
            self.assertTrue(result['stderr'])

    def test_unused_volatile_macro_does_not_disable_stable_reuse(self):
        self.source.write_text('#define UNUSED __TIME__\nint main(void){return 0;}\n')
        for hit in [False, True]:
            result, actual = self.compile([])
            self.assertEqual(actual, 0)
            self.assertEqual(result['cache_hit'], hit, result)

    def test_compiler_prefix_mutation_bypasses(self):
        self.source.write_text('int main(void){return VALUE;}\n')
        wrapper = self.root / 'wrapper'
        for number in [11, 11, 12]:
            wrapper.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo inert-wrapper; exit; fi\n'
                               'exec cc -DVALUE=' + str(number) + ' "$@"\n')
            wrapper.chmod(0o755)
            for prefix in [['env', str(wrapper)], ['env', '-u', 'SWR_UNUSED', str(wrapper)], [str(wrapper)]]:
                self.guard()
                result = dev_cache.compile_cached([*prefix, str(self.source), '-o', str(self.output)],
                                                  output=self.output, scratch=self.root)
                self.assertEqual(result['returncode'], 0, result)
                self.assertIsNone(result['cache_key'])
                self.assertFalse(result['cache_hit'])
                self.assertIn('wrapper/prefix', result['cache_reason'])
                self.assertEqual(subprocess.run([str(self.output)], timeout=10).returncode, number)

    @unittest.skipUnless(sys.platform == 'darwin', 'Mach-O linker alias fixture')
    def test_auxiliary_linker_mutation_bypasses_reuse(self):
        self.source.write_text('int one(void){return 11;} int two(void){return 12;} '
                               'int value(void); int main(void){return value();}\n')
        wrapper = self.root / 'ld-wrapper'
        for function, expected in [('one', 11), ('one', 11), ('two', 12)]:
            wrapper.write_text('#!/bin/sh\nexec /usr/bin/ld -alias _' + function + ' _value "$@"\n')
            wrapper.chmod(0o755)
            result, actual = self.compile(['-fuse-ld=' + str(wrapper)])
            self.assertEqual(actual, expected)
            self.assertFalse(result['cache_hit'])
            self.assertIsNone(result['cache_key'])
            self.assertIn('untracked', result['cache_reason'])

    def test_indirect_formats_and_unknown_link_flags_refuse_reuse(self):
        for name, content in [('thin.a', b'!<thin>\n'), ('script.so', b'INPUT(other.o)\n')]:
            path = self.root / name; path.write_bytes(content)
            self.assertIn('indirect', dev_cache.unsupported_link_input(['cc', str(self.source), str(path)]))
        for option in ['-Wl,-T,script.ld', '-Xlinker', '-framework', '-Lsearch', '-lvalue', '-MMD', '-oother', '-fuse-ld=private-ld',
                       '--ld-path=private-ld', '-Btools', '-specs=private.spec', '--gcc-toolchain=private']:
            self.assertIsNotNone(dev_cache.unsupported_link_input(['cc', option, str(self.source)]), option)
        self.assertIsNone(dev_cache.unsupported_link_input(['cc', '-Wl,-dead_strip', str(self.source)]))
