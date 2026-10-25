"""Missing/stale new storage dependencies cannot become a PHP SDK syntax pass."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('collection_sdk',Path(__file__).with_name('sdk.py'))
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)
class MemoryDependency(unittest.TestCase):
    def test_missing_concrete_header_stops_before_private_mirror_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);directory=root/'migration/patches/memory';directory.mkdir(parents=True)
            (directory/'manifest.json').write_text(json.dumps({'upstream_commit':sdk.PIN,'patches':[]}))
            with patch.object(sdk,'ROOT',root),patch.object(sdk.subprocess,'run') as run,self.assertRaisesRegex(ValueError,'Concrete TableV2'):
                sdk.memory_headers(root/'missing-mirror')
            run.assert_not_called();self.assertFalse((root/'missing-mirror').exists())
    def test_wrong_dependency_pin_or_checksum_stops_before_mirror_mutation(self):
        for invalid in ['pin','checksum']:
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);directory=root/'migration/patches/memory';directory.mkdir(parents=True)
                (directory/'table.patch').write_text('unqualified')
                (directory/'manifest.json').write_text(json.dumps({'upstream_commit':'wrong' if invalid=='pin' else sdk.PIN,'patches':[{'path':'table.patch','sha256':'wrong','upstream_paths':['include/swoole_table.h']}]}))
                with patch.object(sdk,'ROOT',root),patch.object(sdk.subprocess,'run') as run,self.assertRaisesRegex(ValueError,'dependency (pin|checksum)'):
                    sdk.memory_headers(root/'missing-mirror')
                run.assert_not_called();self.assertFalse((root/'missing-mirror').exists())
if __name__=='__main__':unittest.main()
