"""Bind real directory storage selection to independent artifacts and full plans."""
import hashlib
import json
from itertools import product
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import dev

ROOT = Path(__file__).resolve().parents[2]


class LegacyDirectorySelection(unittest.TestCase):
    def test_combinations_bind_independent_builds_and_keep_originals(self):
        variants = set()
        for directory, config, rewrite in product([False, True], repeat=3):
            args = SimpleNamespace(lane='integrate', module=['http', 'corebase'], php='php', php_extension=[],
                                   jobs=2, test=None, case=None, benchmark=False,
                                   compare=False, stdext=False, fix_halfclose=False,
                                   http_legacy_directory_store=directory,
                                   http_static_config=config, http_rewrite_store=rewrite)
            commands = dict(dev.plan(args, ROOT/'target/reports/directory-selection-test'))
            self.assertEqual('--http-legacy-directory-store' in commands['build'], directory)
            self.assertNotIn('--http-legacy-directory-store', commands['reference-build'])
            self.assertEqual('http-legacy-directory-store' in commands, directory)
            self.assertEqual('http-legacy-directory-sdk' in commands, directory)
            if directory:
                gate = commands['http-legacy-directory-store']
                self.assertIn('--archive', gate)
                self.assertTrue(gate[gate.index('--archive')+1].endswith('/rust-prefix/lib/libswoole_rs_ffi.a'))
                self.assertNotIn('--sanitize', gate)  # This runner always uses Native ASan.
            for name in ['http-full-originals', 'http-coro-full-originals', 'http-directory']:
                self.assertIn(name, commands)
            variants.add(dev.build_variant(args))
        self.assertEqual(len(variants), 8)

    def test_artifact_reuse_refuses_mixed_selected_or_native_modes(self):
        for requested, selected, native, accepted in [(False,False,False,True),
                (True,True,False,True), (True,False,False,False),
                (False,True,False,False), (True,True,True,False)]:
            with self.subTest(requested=requested, selected=selected, native=native), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                args = SimpleNamespace(lane='integrate', module=['http'], stdext=False,
                    fix_halfclose=False, http_legacy_directory_store=requested, artifacts_from=root/'exports')
                for label, variant in [('selected',dev.build_variant(args)),('native','upstream')]:
                    folder=args.artifacts_from/(label+'-export');folder.mkdir(parents=True)
                    manifest=json.dumps(dict(build_mode='immutable',configure=[],inputs=dict(
                        modules=['http'],fix_halfclose=False,
                        http_legacy_directory_store_requested=selected if label=='selected' else native))).encode()
                    files={}
                    for name,data in [('build-manifest.json',manifest),('swoole.so',b'fixture')]:
                        (folder/name).write_bytes(data);files[name]={'sha256':hashlib.sha256(data).hexdigest()}
                        p=root/'target/hybrid'/variant/('modules/swoole.so' if name=='swoole.so' else name)
                        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                    (folder/'export.json').write_text(json.dumps(dict(source_ref='frozen',files=files)))
                with patch.object(dev,'ROOT',root),patch.object(dev.subprocess,'check_output',return_value='frozen\n'):
                    if accepted:self.assertEqual(set(dev.verify_artifact_report(args)),{'native','selected'})
                    else:
                        with self.assertRaisesRegex(ValueError,'Artifact configuration differs'):dev.verify_artifact_report(args)

    def test_dependency_refused_before_build(self):
        for command in [[sys.executable,'tools/dev.py','integrate','--module','reactor','--plan'],
                        [sys.executable,'tools/build_hybrid.py','--module','reactor'],
                        [sys.executable,'tools/build_hybrid.py','--backend','upstream','--module','http']]:
            result=subprocess.run(command+['--http-legacy-directory-store'],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertIn('--http-legacy-directory-store requires',result.stderr)
