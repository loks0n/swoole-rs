"""Reject an unsupported sanitizer declaration before any source/native execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('buffer_facade',Path(__file__).with_name('facade.py'))
facade=importlib.util.module_from_spec(spec);spec.loader.exec_module(facade)
class InstrumentationDeclaration(unittest.TestCase):
    def test_uninstrumented_archive_cannot_claim_rust_asan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'ordinary.a';archive.write_bytes(b'ordinary candidate');output=root/'report.json'
            argv=['facade.py','--source','/missing/pinned','--archive',str(archive),'--sanitize','--rust-asan','--output',str(output)]
            with patch('sys.argv',argv),patch.object(facade.platform,'platform',return_value='test-host'),patch.object(facade.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run,patch.object(facade.subprocess,'check_output') as read:
                self.assertEqual(facade.main(),1);run.assert_called_once_with(['nm','-u',str(archive)],capture_output=True,text=True);read.assert_not_called()
            result=json.loads(output.read_text());self.assertFalse(result['passed']);self.assertEqual(result['engines'],{});self.assertIn('lacks Rust ASan',result['error'])
if __name__=='__main__':unittest.main()
