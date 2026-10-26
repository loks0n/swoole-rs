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
        for typed, static, rewrite in product([False, True], repeat=3):
            args = SimpleNamespace(lane='integrate', module=['buffer', 'reactor', 'http'], all_modules=False,
                                   php='php', php_extension=[], jobs=2, test=None, case=None,
                                   benchmark=False, compare=False, fix_halfclose=False,
                                   buffer_typed=typed, http_static_config=static, http_rewrite_store=rewrite)
            commands = dict(dev.plan(args, ROOT/'target/reports/typed-unit'))
            self.assertEqual('--buffer-typed' in commands['build'], typed)
            self.assertNotIn('--buffer-typed', commands['reference-build'])
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
        self.assertEqual(len(variants), 8)

    def test_reuse_requires_exact_native_and_selected_configuration(self):
        for capability in ['buffer_typed']:
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
