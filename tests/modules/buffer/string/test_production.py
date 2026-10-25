"""A copied SDK must refuse stale export files before any Git/compile work."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('string_production', Path(__file__).with_name('production.py'))
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


class FrozenHeaders(unittest.TestCase):
    def test_existing_production_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'failure.json';output.write_text('preserved-first-failure')
            arguments=['production.py','--source','/unused','--source-ref','a'*40,'--engine','native=/unused.so','--build-manifest','/unused-manifest','--archive','/unused.a','--selected-export','/unused-export','--native-export','/unused-native-export','--consumer','compatibility','--output',str(output)]
            with patch.object(production.sys,'argv',arguments),patch.object(production,'Engine') as engine:
                with self.assertRaises(SystemExit):production.main()
                engine.assert_not_called()
            self.assertEqual(output.read_text(),'preserved-first-failure')

    def test_compatibility_addon_preserves_qualified_44_statement_body(self):
        directory=Path(__file__).parent
        standalone=(directory/'compatibility.cc').read_text()
        addon=(directory/'compatibility-production.cc').read_text()
        expected=standalone[standalone.index('    unsigned checks=0;'):standalone.index('    std::cout<<')]
        actual=addon[addon.index('    unsigned checks=0;'):addon.index('        add_assoc_long(return_value,"checks",checks);')]
        self.assertEqual(actual,expected)

    def test_old_compatibility_producer_refuses_before_any_engine_or_compiler(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);manifest=directory/'old-manifest.json';manifest.write_text(json.dumps(dict(inputs=dict(rust_sources_sha256={}))))
            output=directory/'refusal.json'
            arguments=['production.py','--source','/unused','--source-ref','a'*40,'--engine','native=/unused.so','--engine','selected=/unused-selected.so','--build-manifest',str(manifest),'--archive','/unused.a','--selected-export','/unused-export','--native-export','/unused-native-export','--consumer','compatibility','--output',str(output)]
            with patch.object(production.sys,'argv',arguments),patch.object(production,'Engine') as engine,patch.object(production,'run_isolated') as run,patch.object(production.subprocess,'check_output') as command:
                self.assertEqual(production.main(),1)
                engine.assert_not_called();run.assert_not_called();command.assert_not_called()
            self.assertIn('older producers',json.loads(output.read_text())['error'])

    def test_compatibility_needs_new_source_and_exact_inventory(self):
        for manifest in [{},dict(inputs={}),dict(inputs=dict(rust_sources_sha256={})),dict(inputs=dict(rust_sources_sha256={'crates/buffer/src/string/compatibility.rs':'bad'}))]:
            with self.assertRaisesRegex(ValueError,'older producers'):
                production.compatibility_inputs(manifest)
        valid=dict(inputs=dict(rust_sources_sha256={'crates/buffer/src/string/compatibility.rs':'a'*64}))
        self.assertEqual(production.compatibility_inputs(valid)['sha256'],'a'*64)
        self.assertTrue(production.consumer_inventory('compatibility',dict(checks=44,selected_origin_checks=1),True))
        self.assertTrue(production.consumer_inventory('compatibility',dict(checks=44,selected_origin_checks=0),False))
        for row in [{},dict(checks=43,selected_origin_checks=1),dict(checks=44,selected_origin_checks=0)]:
            self.assertFalse(production.consumer_inventory('compatibility',row,True))

    def test_ownership_refuses_truncated_or_wrong_engine_inventory(self):
        self.assertTrue(production.consumer_inventory('ownership', dict(checks=13, selected_origin_checks=0), False))
        self.assertTrue(production.consumer_inventory('ownership', dict(checks=13, selected_origin_checks=2), True))
        for row in [{}, dict(checks=12, selected_origin_checks=2), dict(checks=13, selected_origin_checks=0)]:
            self.assertFalse(production.consumer_inventory('ownership', row, True))
        self.assertFalse(production.consumer_inventory('ownership', dict(checks=13, selected_origin_checks=2), False))

    def test_allocation_refuses_truncated_or_missing_selected_origin(self):
        self.assertTrue(production.consumer_inventory('allocation', dict(checks=12, selected_origin_checks=1), True))
        self.assertTrue(production.consumer_inventory('allocation', dict(checks=12, selected_origin_checks=0), False))
        for row in [{}, dict(checks=11, selected_origin_checks=1), dict(checks=12, selected_origin_checks=0)]:
            self.assertFalse(production.consumer_inventory('allocation', row, True))

    def test_format_refuses_truncated_or_missing_selected_origin(self):
        self.assertTrue(production.consumer_inventory('format', dict(checks=604, selected_origin_checks=2), True))
        self.assertTrue(production.consumer_inventory('format', dict(checks=604, selected_origin_checks=0), False))
        for row in [{}, dict(checks=603, selected_origin_checks=2), dict(checks=604, selected_origin_checks=0)]:
            self.assertFalse(production.consumer_inventory('format', row, True))

    def export(self, directory):
        for name in ['config.h', 'build-manifest.json', 'swoole.so']:
            (directory / name).write_text('original-' + name)
        path = directory / 'export.json'
        path.write_text(json.dumps(dict(source_ref='exact-source', files={name: dict(sha256=production.sha(directory / name))
                    for name in ['config.h', 'build-manifest.json', 'swoole.so']})))
        return path

    def test_changed_config_extension_or_manifest_refuses_before_reconstruction(self):
        for name in ['config.h', 'build-manifest.json', 'swoole.so']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                export = self.export(directory)
                (directory / name).write_text('changed')
                with patch.object(production.subprocess, 'check_output') as command:
                    with self.assertRaisesRegex(ValueError, 'Export input changed'):
                        production.headers(Path('/unused'), export, directory / 'build-manifest.json', directory / 'mirror')
                    command.assert_not_called()
                self.assertFalse((directory / 'mirror').exists())

    def test_export_for_another_manifest_cannot_supply_headers(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            export = self.export(directory)
            other = directory / 'other.json'
            other.write_text('different actual manifest')
            with patch.object(production.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(ValueError, 'actual manifest'):
                    production.headers(Path('/unused'), export, other, directory / 'mirror')
                command.assert_not_called()


class BorrowedImmutableExports(unittest.TestCase):
    def export(self, directory):
        directory.mkdir(exist_ok=True)
        (directory / 'swoole.so').write_bytes(b'fixture DSO identity only; never loaded')
        (directory / 'config.h').write_text('configured fixture')
        (directory / 'build-manifest.json').write_text(json.dumps(dict(extension_sha256=production.sha(directory / 'swoole.so'))))
        export = directory / 'export.json'
        export.write_text(json.dumps(dict(source_ref='a' * 40, files={name: dict(sha256=production.sha(directory / name)) for name in ['swoole.so','config.h','build-manifest.json']})))
        return export

    def test_borrowed_exact_export_has_before_after_hashes_without_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root)
            with patch.object(production.subprocess, 'check_output', return_value='a' * 40 + '\n'), patch.object(production.shutil, 'copy2') as copy:
                binding = production.immutable_export_input(root / 'swoole.so', [export])
                production.verify_borrowed_input(binding)
                copy.assert_not_called()
            self.assertEqual(binding['before_sha256'], binding['after_sha256'])
            self.assertEqual(binding['extension'], str(root / 'swoole.so'))
            self.assertEqual(binding['source_ref'], 'a' * 40)

    def test_same_bytes_at_unidentified_path_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root / 'export')
            other = root / 'mutable-alias.so'
            other.write_bytes((export.parent / 'swoole.so').read_bytes())
            with self.assertRaisesRegex(ValueError, 'exact identified export DSO'):
                production.immutable_export_input(other, [export])

    def test_extension_and_parent_symlink_aliases_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root / 'export')
            alias = root / 'alias.so'
            alias.symlink_to(export.parent / 'swoole.so')
            parent = root / 'mutable-build-alias'
            parent.symlink_to(export.parent, target_is_directory=True)
            for extension, manifest in [(alias, export), (parent / 'swoole.so', parent / 'export.json')]:
                with self.subTest(extension=extension), self.assertRaisesRegex(ValueError, 'not an alias'):
                    production.immutable_export_input(extension, [manifest])

    def test_stale_member_refuses_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root)
            (root / 'config.h').write_text('changed')
            with patch.object(production.subprocess, 'check_output', return_value='a' * 40), self.assertRaisesRegex(ValueError, 'input changed'):
                production.immutable_export_input(root / 'swoole.so', [export])

    def test_mutation_after_binding_fails_and_records_observed_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root)
            with patch.object(production.subprocess, 'check_output', return_value='a' * 40):
                binding = production.immutable_export_input(root / 'swoole.so', [export])
            (root / 'config.h').write_text('changed later')
            with self.assertRaisesRegex(ValueError, 'changed during'):
                production.verify_borrowed_input(binding)
            self.assertNotEqual(binding['before_sha256'], binding['after_sha256'])

    def test_missing_source_or_unbound_manifest_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            export = self.export(root)
            with patch.object(production.subprocess, 'check_output', return_value='b' * 40), self.assertRaisesRegex(ValueError, 'source is unavailable or differs'):
                production.immutable_export_input(root / 'swoole.so', [export])
            (root / 'build-manifest.json').write_text(json.dumps(dict(extension_sha256='wrong')))
            data = json.loads(export.read_text())
            data['files']['build-manifest.json']['sha256'] = production.sha(root / 'build-manifest.json')
            export.write_text(json.dumps(data))
            with patch.object(production.subprocess, 'check_output', return_value='a' * 40), self.assertRaisesRegex(ValueError, 'manifest does not identify'):
                production.immutable_export_input(root / 'swoole.so', [export])


class DirectFieldsSourceAdmission(unittest.TestCase):
    def pair(self, directory):
        source='a'*40
        raw={'crates/buffer/src/string/fields.rs':b'initialized scalar source fixture; never executed',
             'native/buffer/swoole_rs_string_fields.h':b'typed opaque schema fixture',
             'migration/patches/buffer/0003-string-storage.patch':b'actual caller patch fixture'}
        digest=lambda name:production.hashlib.sha256(raw[name]).hexdigest()
        inputs=dict(string_direct_fields_requested=True,
            rust_sources_sha256={'crates/buffer/src/string/fields.rs':digest('crates/buffer/src/string/fields.rs')},
            headers_sha256={'native/buffer/swoole_rs_string_fields.h':digest('native/buffer/swoole_rs_string_fields.h')},
            patches=[dict(path='migration/patches/buffer/0003-string-storage.patch',
                sha256=digest('migration/patches/buffer/0003-string-storage.patch'),
                upstream_paths=['src/core/string.cc','include/swoole_string.h'])])
        manifest=dict(inputs=inputs)
        exports=[]
        for name, enabled in [('selected',True),('native',False)]:
            target=directory/name;target.mkdir()
            (target/'config.h').write_text('#define SWOOLE_RS_STRING_DIRECT_FIELDS 1\n' if enabled else '/* #undef SWOOLE_RS_STRING_DIRECT_FIELDS */\n')
            (target/'swoole.so').write_bytes(b'identity fixture only; NEVER LOADED')
            (target/'build-manifest.json').write_text(json.dumps(manifest if enabled else dict(inputs={})))
            export=target/'export.json';exports.append(export)
            self.bind(export,source)
        return manifest,exports,source,raw

    def bind(self, export, source='a'*40):
        export.write_text(json.dumps(dict(source_ref=source,files={name:dict(sha256=production.sha(export.parent/name))
            for name in ['config.h','swoole.so','build-manifest.json']})))

    def git(self, raw):
        def read(args, **kwargs):
            self.assertEqual(args[:2],['git','show'])
            return raw[args[2].split(':',1)[1]]
        return read

    def test_exact_source_macro_and_two_manifest_modes_are_bound_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest,exports,source,raw=self.pair(Path(tmp))
            with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)) as command:
                result=production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')
            self.assertEqual(command.call_count,3)
            self.assertEqual([row['actual_macro'] for row in result['configs']],[1,0])
            self.assertEqual(set(result['sources']),set(raw))

    def test_literal_option_mode_consumer_and_source_sha_refuse_before_git(self):
        variants=[(False,True,'compatibility','a'*40),(True,False,'compatibility','a'*40),
                  (True,True,'format','a'*40),(True,True,'compatibility','main'),
                  (True,'true','compatibility','a'*40)]
        for required,requested,consumer,source in variants:
            with self.subTest(required=required,requested=requested,consumer=consumer), patch.object(production.subprocess,'check_output') as command:
                with self.assertRaises(ValueError):
                    production.direct_fields_inputs(dict(inputs=dict(string_direct_fields_requested=requested)),Path('/unused'),Path('/unused'),source,required,consumer)
                command.assert_not_called()

    def test_missing_or_wrong_concrete_source_and_caller_overlay_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest,exports,source,raw=self.pair(Path(tmp))
            with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)):
                manifest['inputs']['headers_sha256']['native/buffer/swoole_rs_string_fields.h']='b'*64
                with self.assertRaisesRegex(ValueError,'differs from compiled manifest'):
                    production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')
                manifest['inputs']['headers_sha256'].clear()
                with self.assertRaisesRegex(ValueError,'concrete source identity'):
                    production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')

    def test_missing_actual_caller_destination_refuses_before_any_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest,exports,source,raw=self.pair(Path(tmp));manifest['inputs']['patches'][0]['upstream_paths']=['include/swoole_string.h']
            with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)),self.assertRaisesRegex(ValueError,'actual String caller overlay'):
                production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')

    def test_zero_ambiguous_unknown_or_native_enabled_macro_refuses(self):
        cases=[(0,'#define SWOOLE_RS_STRING_DIRECT_FIELDS 0\n'),
               (0,'#define SWOOLE_RS_STRING_DIRECT_FIELDS (1)\n'),
               (0,'#define SWOOLE_RS_STRING_DIRECT_FIELDS 1\n#define SWOOLE_RS_STRING_DIRECT_FIELDS 0\n'),
               (1,'#define SWOOLE_RS_STRING_DIRECT_FIELDS 1\n')]
        for index,config in cases:
            with self.subTest(index=index,config=config),tempfile.TemporaryDirectory() as tmp:
                manifest,exports,source,raw=self.pair(Path(tmp));(exports[index].parent/'config.h').write_text(config);self.bind(exports[index])
                with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)),self.assertRaisesRegex(ValueError,'SDK macro'):
                    production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')

    def test_stale_config_and_native_requested_identity_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest,exports,source,raw=self.pair(Path(tmp));(exports[0].parent/'config.h').write_text('changed')
            with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)),self.assertRaisesRegex(ValueError,'input changed'):
                production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')
        with tempfile.TemporaryDirectory() as tmp:
            manifest,exports,source,raw=self.pair(Path(tmp));(exports[1].parent/'build-manifest.json').write_text(json.dumps(dict(inputs=dict(string_direct_fields_requested=True))));self.bind(exports[1])
            with patch.object(production.subprocess,'check_output',side_effect=self.git(raw)),self.assertRaisesRegex(ValueError,'selected ON and Native OFF'):
                production.direct_fields_inputs(manifest,*exports,source,True,'compatibility')

    def test_old_direct_producer_refuses_before_engine_or_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(inputs={})));output=root/'refused.json'
            args=['production.py','--source','/unused','--source-ref','a'*40,'--engine','native=/unused.so','--engine','selected=/unused-selected.so',
                  '--build-manifest',str(manifest),'--archive','/unused.a','--selected-export','/unused-export','--native-export','/unused-native-export',
                  '--consumer','compatibility','--require-direct-fields','--output',str(output)]
            with patch.object(production.sys,'argv',args),patch.object(production,'Engine') as engine,patch.object(production,'run_isolated') as run,patch.object(production.subprocess,'check_output') as command:
                self.assertEqual(production.main(),1);engine.assert_not_called();run.assert_not_called();command.assert_not_called()
            self.assertIn('literal --require-direct-fields',json.loads(output.read_text())['error'])


if __name__ == '__main__':
    unittest.main()
