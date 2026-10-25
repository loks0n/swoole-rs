"""Compiler-free staging/extraction proof for the actual mapping transaction."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('mapping_operation', Path(__file__).with_name('mapping_operation.py'))
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
SOURCE = None
PROOFS = []


class MappingStaging(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mapping-staging-test-')
        self.addCleanup(self.temporary.cleanup)
        parent = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(parent)], check=True)
        (parent / '.gitignore').write_text('target/\n')
        self.tree = parent / 'target/selected'
        original = self.tree / driver.SOURCE
        original.parent.mkdir(parents=True)
        original.write_bytes(subprocess.check_output(['git', '-C', str(SOURCE), 'show', driver.PIN + ':' + driver.SOURCE]))
        self.entry = next(p for p in json.loads((driver.ROOT / 'migration/patches/memory/manifest.json').read_text())['patches'] if driver.SOURCE in p['upstream_paths'])
        self.patch = driver.ROOT / 'migration/patches/memory' / self.entry['path']

    def test_actual_overlay_and_complete_body_extraction_in_ignored_parent(self):
        proof = driver.apply_patch_verified(self.tree, self.patch, self.entry['upstream_paths'], self.entry['sha256'])
        self.assertNotEqual(proof['before'], proof['after'])
        text = (self.tree / driver.SOURCE).read_text()
        model = driver.selected_model(text)
        self.assertIn('namespace model {', model)
        self.assertNotIn('using swoole::SharedMemory', model)
        self.assertNotIn('namespace swoole', model)
        for name in ['sw_shm_malloc', 'sw_shm_calloc', 'sw_shm_free', 'sw_shm_protect', 'sw_shm_realloc']:
            self.assertEqual(model.count(name + '('), text[text.index('struct SharedMemory {'):].count(name + '('))
        self.assertIn('File zerofile("/dev/zero", O_RDWR)', model)
        self.assertIn('swr_v2_memory_mapping_step', model)
        PROOFS.append(proof)

    def test_wrong_patch_identity_refused_before_source_change(self):
        path = self.tree / driver.SOURCE
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed before application'):
            driver.apply_patch_verified(self.tree, self.patch, self.entry['upstream_paths'], '0' * 64)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.tree / '.git').exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite a receipt')
    SOURCE = args.source.resolve(strict=True)
    result = unittest.main(argv=[sys.argv[0]], exit=False, verbosity=2).result
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'passed': result.wasSuccessful(), 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': result.skipped,
        'scope': __doc__, 'runtime_qualified': False, 'patch_proofs': PROOFS}, indent=2) + '\n')
    raise SystemExit(not result.wasSuccessful())
