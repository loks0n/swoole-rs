"""Source staging remains pinned, checksummed and limited to the two facades."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('phpcollections_gate',Path(__file__).with_name('gate.py'))
gate=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(gate)

class Staging(unittest.TestCase):
    def test_snapshot_retains_independent_source_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rust=root/'crates/phpcollections/src/lib.rs';rust.parent.mkdir(parents=True);rust.write_text('source before edit')
            header=root/'native/phpcollections/swoole_rs_phpcollections.h';header.parent.mkdir(parents=True);header.write_text('header')
            work=root/'work';work.mkdir()
            with patch.object(gate,'ROOT',root):snapshot=gate.snapshot_inputs(work)
            rust.write_text('source after edit')
            self.assertEqual(snapshot['lib.rs'].read_text(),'source before edit')

    def test_missing_input_does_not_publish_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);work=root/'work';work.mkdir()
            with patch.object(gate,'ROOT',root),self.assertRaises(FileNotFoundError):gate.snapshot_inputs(work)
            self.assertEqual(list(work.iterdir()),[])

    def test_wrong_pin_refuses_before_source_or_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);directory=root/'migration/patches/phpcollections';directory.mkdir(parents=True)
            (directory/'manifest.json').write_text(json.dumps({'upstream_commit':'wrong','patches':[]}))
            with patch.object(gate,'ROOT',root),self.assertRaisesRegex(ValueError,'pin differs'):
                gate.stage(root/'absent-source',root/'work')
            self.assertFalse((root/'work').exists())

    def test_checksum_refuses_before_source_or_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);directory=root/'migration/patches/phpcollections';directory.mkdir(parents=True)
            (directory/'x.patch').write_text('not qualified')
            (directory/'manifest.json').write_text(json.dumps({'upstream_commit':gate.PIN,'patches':[{'path':'x.patch','sha256':'wrong','upstream_paths':['ext-src/swoole_table.cc']}]}))
            with patch.object(gate,'ROOT',root),self.assertRaisesRegex(ValueError,'checksum differs'):
                gate.stage(root/'absent-source',root/'work')
            self.assertFalse((root/'work').exists())

if __name__=='__main__':unittest.main()
