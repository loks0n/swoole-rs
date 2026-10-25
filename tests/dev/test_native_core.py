"""Native original receipts must not turn skipped, foreign or failed assertions green."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import native_core


class NativeOriginals(unittest.TestCase):
    def test_stat_adapter_is_explicit_and_limited_to_original_http_test_unit(self):
        tree = Path('/private/native')
        self.assertEqual(native_core.stat_adapter(tree,False,'Linux'),'')
        with self.assertRaisesRegex(ValueError,'only valid on Darwin'):
            native_core.stat_adapter(tree,True,'Linux')
        adapter = native_core.stat_adapter(tree,True,'Darwin')
        self.assertIn('core-tests/src/server/http_server.cpp',adapter)
        self.assertIn('COMPILE_DEFINITIONS "st_mtim=st_mtimespec"',adapter)
        self.assertNotIn('add_definitions',adapter)

    def test_cache_rejects_mutated_library_and_retargeted_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root/'core-tests'; binary.write_bytes(b'executable')
            first = root/'libswoole.1.so'; first.write_bytes(b'library')
            second = root/'libswoole.2.so'; second.write_bytes(b'library')
            library = root/'libswoole.so'; library.symlink_to(first)
            receipt = root/'receipt.json'
            import json
            receipt.write_text(json.dumps({'binary_sha256':native_core.sha(binary),
                                          'native_library':native_core.library_identity(library)}))
            self.assertTrue(native_core.valid_build_receipt(receipt,binary,library))
            first.write_bytes(b'mutated library')
            self.assertFalse(native_core.valid_build_receipt(receipt,binary,library))
            first.write_bytes(b'library')
            library.unlink(); library.symlink_to(second)
            self.assertFalse(native_core.valid_build_receipt(receipt,binary,library))
            receipt.write_text(json.dumps({'binary_sha256':native_core.sha(binary)}))
            self.assertFalse(native_core.valid_build_receipt(receipt,binary,library))

    def test_loader_requires_expected_library_on_both_platforms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for system, name in [('Darwin','libswoole.6.2.2.dylib'),('Linux','libswoole.so.6')]:
                library = root/name; library.write_bytes(b'expected')
                foreign = root/'foreign'/name; foreign.parent.mkdir(exist_ok=True); foreign.write_bytes(b'expected')
                expected = native_core.library_identity(library)
                def output(path):
                    return (f'dyld[123]: <UUID> {path}\n' if system == 'Darwin'
                            else f'\tlibswoole.so.6 => {path} (0x00007abc)\n')
                native_core.verify_loader_output(output(library),expected,system)
                for text in ['',output(foreign),output(library)+output(foreign)]:
                    with self.assertRaisesRegex(ValueError,'foreign'):
                        native_core.verify_loader_output(text,expected,system)
                library.write_bytes(b'changed during probe')
                with self.assertRaisesRegex(ValueError,'changed'):
                    native_core.verify_loader_output(output(library),expected,system)

    def test_xml_preserves_failure_skip_and_disabled_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'original.xml'
            base = '<testcase classname="reactor" name="wait" status="run" result="completed">{}</testcase>'
            for content, code, expected in [('',0,'passed'),('<failure message="original"/>',0,'failed'),
                                             ('<skipped message="unavailable"/>',0,'skipped'),('',1,'failed')]:
                path.write_text('<testsuites>'+base.format(content)+'</testsuites>')
                self.assertEqual(native_core.test_outcome(path,'reactor.wait',code)['status'],expected)
            path.write_text('<testcase classname="reactor" name="wait" status="notrun" result="suppressed"/>')
            self.assertEqual(native_core.test_outcome(path,'reactor.wait',0)['status'],'skipped')
            for content in ['<broken', '<testsuites/>', '<testsuites>'+base.format('')*2+'</testsuites>',
                            base.format('').replace('name="wait"','name="foreign"'),
                            base.format('').replace('status="run"','status="unknown"')]:
                path.write_text(content)
                self.assertEqual(native_core.test_outcome(path,'reactor.wait',0)['status'],'failed')
            path.unlink()
            self.assertEqual(native_core.test_outcome(path,'reactor.wait',0)['status'],'failed')

    def test_original_argv_root_finds_pinned_fixture_without_binary_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); build=root/'build/bin';build.mkdir(parents=True)
            binary=build/'core-tests';binary.write_bytes(b'exact original executable');binary.chmod(0o755)
            tree=root/'src';fixture=tree/'examples/test.jpg';fixture.parent.mkdir(parents=True);fixture.write_bytes(b'pinned fixture')
            executable=native_core.fixture_binary(binary,tree)
            self.assertEqual(executable.read_bytes(),binary.read_bytes())
            self.assertTrue(os.access(executable,os.X_OK))
            self.assertEqual((executable.parent/'../examples/test.jpg').resolve().read_bytes(),b'pinned fixture')
            executable.write_bytes(b'stale prior launcher')
            self.assertEqual(native_core.fixture_binary(binary,tree).read_bytes(),binary.read_bytes())

    def test_inventory_keeps_parameterized_names_and_rejects_duplicates(self):
        text = 'Running main()\nreactor.\n  wait\nTyped/0.  # TypeParam = int\n  check  # ignored annotation\n'
        self.assertEqual(native_core.inventory_from_listing(text),['reactor.wait','Typed/0.check'])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            native_core.inventory_from_listing('reactor.\n  wait\n  wait\n')

    def test_staging_uses_all_pinned_blobs_and_modes_without_mutating_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source=root/'source'; source.mkdir()
            (source/'core-tests').mkdir(); original=source/'core-tests/original.cpp'
            original.write_bytes(b'original assertion\x00bytes')
            script=source/'script';script.write_text('#!/bin/sh\nexit 0\n');script.chmod(0o755)
            (source/'link').symlink_to('script')
            (source/'.gitattributes').write_text('core-tests export-ignore\n')
            subprocess.run(['git','init','-q',str(source)],check=True)
            subprocess.run(['git','-C',str(source),'add','.'],check=True)
            subprocess.run(['git','-C',str(source),'-c','user.name=Fixture','-c','user.email=fixture@local.invalid','commit','-qm','pin'],check=True)
            pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
            original.write_text('uncommitted mutation')
            with patch.object(native_core,'COMMIT',pin):
                receipts=native_core.stage(source,root/'staged')
            self.assertEqual((root/'staged/core-tests/original.cpp').read_bytes(),b'original assertion\x00bytes')
            self.assertIn('core-tests/original.cpp',receipts)
            self.assertTrue(os.access(root/'staged/script',os.X_OK))
            self.assertEqual(os.readlink(root/'staged/link'),'script')
            self.assertEqual(original.read_text(),'uncommitted mutation')


if __name__ == '__main__':
    unittest.main()
