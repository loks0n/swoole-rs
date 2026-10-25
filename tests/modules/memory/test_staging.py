"""Compiler-free actual-overlay witnesses; no Native memory profiles execute."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import digest

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
SOURCE = ROOT / 'target/upstream/src'
PROOFS = []


def driver(name):
    spec = importlib.util.spec_from_file_location('memory_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MemoryStaging(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='memory-overlay-test-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        (root / '.gitignore').write_text('target/\n')
        self.tree = root / 'target/selected'
        self.tree.mkdir(parents=True)
        self.entries = json.loads((ROOT / 'migration/patches/memory/manifest.json').read_text())['patches']

    def populate(self, entries):
        for name in sorted({name for entry in entries for name in entry['upstream_paths']}):
            path = self.tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(['git', '-C', str(SOURCE), 'show', PIN + ':' + name], timeout=15))

    def verify(self, module, entries):
        self.populate(entries)
        proofs = module.apply_overlays(self.tree, entries)
        self.assertEqual(len(proofs), len(entries))
        self.assertTrue((self.tree / '.git').is_dir())
        for entry, proof in zip(entries, proofs):
            self.assertEqual(proof['patch_sha256'], entry['sha256'])
            self.assertEqual(set(proof['after']), set(entry['upstream_paths']))
            for name in entry['upstream_paths']:
                self.assertNotEqual(proof['before'][name], proof['after'][name])
                self.assertEqual(proof['after'][name], digest(self.tree / name))
        PROOFS.append({'driver': module.__name__, 'proofs': proofs})

    def test_full_gate_actual_overlays_in_ignored_parent(self):
        self.verify(driver('gate'), self.entries)

    def test_channel_actual_header_overlay_in_ignored_parent(self):
        entries = [entry for entry in self.entries if 'include/swoole_channel.h' in entry['upstream_paths']]
        self.verify(driver('channel_compat'), entries)
        self.assertIn('Memory overlay requires --enable-swoole-rs-memory',
                      (self.tree / 'include/swoole_channel.h').read_text())

    def test_wrong_pin_refused_before_stage_mutation(self):
        entries = [self.entries[0]]
        self.populate(entries)
        before = {name: digest(self.tree / name) for name in entries[0]['upstream_paths']}
        for module in [driver('gate'), driver('channel_compat')]:
            with self.subTest(driver=module.__name__):
                with self.assertRaisesRegex(ValueError, 'changed before application'):
                    module.apply_overlays(self.tree, [{**entries[0], 'sha256': '0' * 64}])
                self.assertFalse((self.tree / '.git').exists())
                self.assertEqual(before, {name: digest(self.tree / name) for name in before})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    SOURCE = args.source.resolve(strict=True)
    program = unittest.main(argv=[sys.argv[0]], exit=False, verbosity=2)
    result = program.result
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'passed': result.wasSuccessful(), 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': result.skipped,
        'pin': PIN, 'scope': __doc__, 'runtime_qualified': False,
        'overlay_proofs': PROOFS}, indent=2) + '\n')
    raise SystemExit(not result.wasSuccessful())
