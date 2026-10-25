"""Source-only M01 overlay regression; no compiler/runtime/fault profile launched."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import staging


def edit_patch(name='src/core/string.cc'):
    return ('diff --git a/'+name+' b/'+name+'\n--- a/'+name+'\n+++ b/'+name+'\n@@ -1 +1 @@\n-native\n+selected\n').encode()


class BufferStaging(unittest.TestCase):
    def fixture(self, root):
        directory=root/'migration/patches/buffer';directory.mkdir(parents=True)
        canonical=directory/'test.patch';canonical.write_bytes(edit_patch())
        (directory/'manifest.json').write_text(json.dumps({'patches':[{'path':canonical.name,'sha256':hashlib.sha256(canonical.read_bytes()).hexdigest(),'upstream_paths':['src/core/string.cc']}]}))
        tree=root/'scratch';target=tree/'src/core/string.cc';target.parent.mkdir(parents=True);target.write_text('native\n')
        return canonical,tree,target

    def test_committed_stale_checksum_refuses_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);canonical,tree,target=self.fixture(root)
            canonical.write_bytes(canonical.read_bytes().replace(b'+selected',b'+different'))
            with patch.object(staging,'ROOT',root),self.assertRaisesRegex(ValueError,'Patch changed'):
                staging.apply_module_patch(tree,canonical)
            self.assertEqual(target.read_text(),'native\n')

    def test_private_override_is_explicit_and_separately_labeled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,tree,target=self.fixture(root);override=root/'private.patch';override.write_bytes(edit_patch())
            with patch.object(staging,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'Explicit private'):
                    staging.apply_module_patch(tree,override)
                proof=staging.apply_module_patch(tree,override,allow_override=True)
            self.assertEqual(target.read_text(),'selected\n')
            self.assertEqual(proof['authority'],'explicit-private-override-not-manifest-qualified')
            self.assertNotEqual(proof['before'],proof['after'])

    def test_private_override_cannot_escape_owned_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,tree,target=self.fixture(root);override=root/'outside.patch';override.write_bytes(edit_patch('src/protected.cc'))
            with patch.object(staging,'ROOT',root),self.assertRaisesRegex(ValueError,'declared module'):
                staging.apply_module_patch(tree,override,allow_override=True)
            self.assertEqual(target.read_text(),'native\n')

    def test_unadvertised_plain_file_header_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);_,tree,target=self.fixture(root);override=root/'mixed.patch'
            override.write_bytes(edit_patch()+b'--- a/src/protected.cc\n+++ b/src/protected.cc\n@@ -1 +1 @@\n-native\n+selected\n')
            with patch.object(staging,'ROOT',root),self.assertRaisesRegex(ValueError,'file headers differ'):
                staging.apply_module_patch(tree,override,allow_override=True)
            self.assertEqual(target.read_text(),'native\n')

    def test_current_all_overlays_nested_and_independent_are_identical(self):
        root=staging.ROOT;manifest=root/'migration/patches/buffer/manifest.json';entries=json.loads(manifest.read_text())['patches']
        common=Path(subprocess.check_output(['git','-C',str(root),'rev-parse','--git-common-dir'],text=True).strip())
        upstream=(root/common).resolve().parent/'target/upstream/src'
        if not upstream.is_dir():self.skipTest('Pinned upstream unavailable on this host')
        pin=json.loads(manifest.read_text())['upstream_commit'];files={name:subprocess.check_output(['git','-C',str(upstream),'show',pin+':'+name]) for entry in entries for name in entry['upstream_paths']}
        (root/'target').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root/'target',prefix='buffer-staging-') as nested,tempfile.TemporaryDirectory() as independent:
            outputs=[]
            for directory in [nested,independent]:
                tree=Path(directory)
                for name,data in files.items():
                    target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                for entry in entries:
                    proof=staging.apply_module_patch(tree,manifest.parent/entry['path'])
                    self.assertEqual(proof['authority'],'committed-module-manifest')
                    self.assertTrue(all(proof['before'][name]!=proof['after'][name] for name in proof['destinations']))
                outputs.append({name:(tree/name).read_bytes() for name in files})
            self.assertEqual(outputs[0],outputs[1])
            self.assertTrue(all(outputs[0][name]!=data for name,data in files.items()))


if __name__=='__main__':unittest.main()
