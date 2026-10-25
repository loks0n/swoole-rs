"""Keep selected static configuration distinct from Native and cached artifacts."""
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


class StaticConfigSelection(unittest.TestCase):
    def test_variants_keep_native_and_complete_original_inventories(self):
        variants = set()
        for selected, rewrite, stdext in product([False, True], repeat=3):
            args = SimpleNamespace(lane='integrate', module=['http', 'corebase'], all_modules=False,
                                   php='php', php_extension=[], jobs=2, test=None, case=None,
                                   benchmark=False, compare=False, stdext=stdext, fix_halfclose=False,
                                   http_static_config=selected, http_rewrite_store=rewrite)
            commands = dict(dev.plan(args, ROOT / 'target/reports/static-config-unit'))
            self.assertEqual('--http-static-config' in commands['build'], selected)
            reference = commands['stdext-reference-build' if stdext else 'reference-build']
            self.assertNotIn('--http-static-config', reference)
            self.assertEqual('http-static-config-context' in commands, selected)
            self.assertEqual('http-static-config-sdk' in commands, selected)
            if selected:
                command = commands['http-static-config-context']
                self.assertIn('--archive', command)
                self.assertIn('--static-config', command)
                self.assertEqual('--rewrite-store' in command, rewrite)
                self.assertNotIn('--sanitize', command)
            for original in ['http-full-originals', 'http-coro-full-originals', 'http-rewrites']:
                self.assertIn(original, commands)
            variants.add(dev.build_variant(args))
        self.assertEqual(len(variants), 8)

    def test_reuse_requires_exact_native_and_selected_configuration(self):
        for requested, stored, native, accepted in [(False, False, False, True),
                                                    (True, True, False, True),
                                                    (True, False, False, False),
                                                    (False, True, False, False),
                                                    (True, True, True, False)]:
            with self.subTest(requested=requested, stored=stored, native=native), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = SimpleNamespace(lane='integrate', module=['http'], all_modules=False,
                                       stdext=False, fix_halfclose=False, http_static_config=requested,
                                       artifacts_from=root/'exports')
                for label, variant in [('selected', dev.build_variant(args)), ('native', 'upstream')]:
                    folder=args.artifacts_from/(label+'-export');folder.mkdir(parents=True)
                    manifest=json.dumps(dict(build_mode='immutable', configure=[], inputs=dict(
                        modules=['http'], fix_halfclose=False,
                        http_static_config_requested=stored if label=='selected' else native))).encode()
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

    def test_dependency_refused_before_build(self):
        commands = [[sys.executable, 'tools/dev.py', 'integrate', '--module', 'reactor', '--http-static-config', '--plan'],
                    [sys.executable, 'tools/build_hybrid.py', '--module', 'reactor', '--http-static-config'],
                    [sys.executable, 'tools/build_hybrid.py', '--backend', 'upstream', '--module', 'http', '--http-static-config']]
        for command in commands:
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn('--http-static-config requires',result.stderr)
