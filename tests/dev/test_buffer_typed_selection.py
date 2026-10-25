"""Keep typed Buffer selection and exact artifact reuse behind its real dependencies."""
import hashlib
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import dev

ROOT = Path(__file__).resolve().parents[2]


class TypedBufferSelection(unittest.TestCase):
    def test_typed_and_http_capabilities_remain_independent(self):
        variants = set()
        for typed, fields, static, rewrite in product([False, True], repeat=4):
            args = SimpleNamespace(lane='integrate', module=['buffer', 'reactor', 'http'], all_modules=False,
                                   php='php', php_extension=[], jobs=2, test=None, case=None,
                                   benchmark=False, compare=False, fix_halfclose=False,
                                   buffer_typed=typed, string_direct_fields=fields, http_static_config=static, http_rewrite_store=rewrite)
            commands = dict(dev.plan(args, ROOT/'target/reports/typed-unit'))
            self.assertEqual('--buffer-typed' in commands['build'], typed)
            self.assertNotIn('--buffer-typed', commands['reference-build'])
            self.assertEqual('--string-direct-fields' in commands['build'], fields)
            self.assertNotIn('--string-direct-fields', commands['reference-build'])
            loaded=commands['string-production-compatibility']
            self.assertEqual('--require-direct-fields' in loaded,fields)
            if fields:
                self.assertRegex(loaded[loaded.index('--source-ref')+1], r'^[0-9a-f]{40}$')
            self.assertEqual('buffer-string-direct-fields' in commands, fields)
            if fields:
                gate = commands['buffer-string-direct-fields']
                self.assertIn('--direct-fields', gate)
                self.assertIn('--sanitize', gate)
                self.assertIn('--archive', gate)
            for name, command in commands.items():
                if 'tests/modules/reactor/production_supported.py' in command:
                    self.assertEqual('--require-typed-buffer' in command, typed, name)
            for phase in ['buffer-typed', 'buffer-typed-layout', 'reactor-buffer-typed-compile']:
                self.assertEqual(phase in commands, typed)
            if typed:
                command=commands['buffer-typed']
                self.assertIn('--sanitize', command)
                self.assertEqual(command[command.index('--archive')+1],
                                 commands['reactor-flush'][commands['reactor-flush'].index('--archive')+1])
                compile_command=commands['reactor-buffer-typed-compile']
                self.assertEqual(compile_command[compile_command.index('--master-patch')+1],
                                 str(ROOT/'migration/patches/integration/0003-server-static-config.patch'))
            for phase in ['reactor-ordered', 'http-full-originals']:
                self.assertIn(phase, commands)
            variants.add(dev.build_variant(args))
        self.assertEqual(len(variants), 16)

    def test_reuse_requires_exact_native_and_selected_configuration(self):
        for capability in ['buffer_typed', 'string_direct_fields']:
            for requested, stored, native, accepted in [(False, False, False, True),
                                                        (True, True, False, True),
                                                        (True, False, False, False),
                                                        (False, True, False, False),
                                                        (True, True, True, False)]:
                with self.subTest(requested=requested, stored=stored, native=native), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    args = SimpleNamespace(lane='integrate', module=['buffer', 'reactor'], all_modules=False,
                                           stdext=False, fix_halfclose=False, **{capability: requested},
                                           artifacts_from=root/'exports')
                    for label, variant in [('selected', dev.build_variant(args)), ('native', 'upstream')]:
                        folder=args.artifacts_from/(label+'-export');folder.mkdir(parents=True)
                        manifest=json.dumps(dict(build_mode='immutable', configure=[], inputs=dict(
                            modules=['buffer', 'reactor'], fix_halfclose=False,
                            **{capability + '_requested': stored if label=='selected' else native}))).encode()
                        files={}
                        for name,data in [('build-manifest.json',manifest),('swoole.so',b'unit fixture only')]:
                            (folder/name).write_bytes(data);files[name]={'sha256':hashlib.sha256(data).hexdigest()}
                            target=root/'target/hybrid'/variant/('modules/swoole.so' if name=='swoole.so' else name)
                            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                        (folder/'export.json').write_text(json.dumps(dict(source_ref='frozen',files=files)))
                    with patch.object(dev,'ROOT',root),patch.object(dev.subprocess,'check_output',return_value='frozen\n'):
                        if accepted:self.assertEqual(set(dev.verify_artifact_report(args)),{'native','selected'})
                        else:
                            with self.assertRaisesRegex(ValueError,'Artifact configuration differs'):dev.verify_artifact_report(args)

    def test_requires_both_actual_rust_subsystems_before_build(self):
        commands = [[sys.executable, 'tools/dev.py', 'integrate', '--module', 'reactor', '--buffer-typed', '--plan'],
                    [sys.executable, 'tools/build_hybrid.py', '--module', 'buffer', '--buffer-typed'],
                    [sys.executable, 'tools/build_hybrid.py', '--backend', 'upstream', '--module', 'buffer', '--module', 'reactor', '--buffer-typed']]
        for command in commands:
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn('--buffer-typed requires',result.stderr)


class StringFieldsSelection(unittest.TestCase):
    def test_dependency_and_unqualified_loaded_profiles_refuse_before_work(self):
        for command, message in [
            ([sys.executable,'tools/build_hybrid.py','--backend','upstream','--module','buffer'], 'requires --backend rust'),
            ([sys.executable,'tools/build_hybrid.py','--module','reactor'], 'requires --backend rust'),
            ([sys.executable,'tools/dev.py','integrate','--module','reactor','--plan'], 'requires --module buffer'),
            ([sys.executable,'tools/dev.py','integrate','--module','buffer','--plan'], 'loaded String profiles other than compatibility are not qualified'),
            ([sys.executable,'tools/dev.py','integrate','--module','buffer','--phase','string-production-random','--plan'], 'loaded String profiles other than compatibility are not qualified')]:
            result=subprocess.run(command+['--string-direct-fields'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn(message,result.stderr)
        result=subprocess.run([sys.executable,'tools/dev.py','integrate','--module','buffer',
            '--string-direct-fields','--phase','buffer-string-direct-fields','--plan'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        phases=json.loads(result.stdout)
        self.assertEqual([p['phase'] for p in phases],['buffer-string-direct-fields'])
        self.assertIn('--direct-fields',phases[0]['command'])
        result=subprocess.run([sys.executable,'tools/dev.py','integrate','--module','buffer',
            '--string-direct-fields','--phase','string-production-compatibility','--plan'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        command=json.loads(result.stdout)[0]['command']
        self.assertIn('--require-direct-fields',command)
        self.assertRegex(command[command.index('--source-ref')+1], r'^[0-9a-f]{40}$')
