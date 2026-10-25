"""Stage current overlays under ignored Git paths; never compile or execute Native code."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from ordered_gate import ROOT, PIN, apply_patch_verified


class ReactorStaging(unittest.TestCase):
    def test_full_overlay_inside_ignored_parent_matches_independent_tree(self):
        manifest = ROOT/'migration/patches/reactor/manifest.json'
        entries = json.loads(manifest.read_text())['patches']
        common = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--git-common-dir'], text=True).strip())
        upstream = (ROOT/common).resolve().parent/'target/upstream/src'
        if not upstream.is_dir():
            self.skipTest('Pinned source is not available on this host')
        files = {name: subprocess.check_output(['git', '-C', str(upstream), 'show', PIN+':'+name])
                 for entry in entries for name in entry['upstream_paths']}
        (ROOT/'target').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'target', prefix='staging-regression-') as nested, tempfile.TemporaryDirectory() as independent:
            outputs = []
            for directory in (nested, independent):
                tree = Path(directory)
                for name, data in files.items():
                    path = tree/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                for entry in entries:
                    proof = apply_patch_verified(tree, manifest.parent/entry['path'], entry['upstream_paths'], entry['sha256'])
                    self.assertEqual(set(proof['before']), set(entry['upstream_paths']))
                    self.assertTrue(all(proof['before'][name] != proof['after'][name] for name in entry['upstream_paths']))
                outputs.append({name: (tree/name).read_bytes() for name in files})
            self.assertEqual(outputs[0], outputs[1])
            self.assertTrue(all(outputs[0][name] != data for name, data in files.items()))


if __name__ == '__main__':
    unittest.main()
