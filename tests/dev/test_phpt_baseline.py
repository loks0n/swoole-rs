"""The PHPT baseline shards every test exactly once and classifies skips by their runner reason."""
import json
from pathlib import Path
import tempfile
import unittest

from corpus.upstream.baseline_summary import category, markdown, rows, skip_reason
from corpus.upstream.inventory import shard


class PhptBaseline(unittest.TestCase):
    def test_shards_partition_every_path(self):
        paths = [f'tests/t/{n}.phpt' for n in range(25)]
        parts = [shard(paths, index, 4) for index in range(1, 5)]
        self.assertEqual(sorted(p for part in parts for p in part), sorted(paths))
        self.assertTrue(all(abs(len(part) - 25 / 4) < 1 for part in parts))

    def test_skips_are_classified_and_only_passed_counts(self):
        detail = 'SKIP x [tests/x.phpt] reason: \x1b[33mmysql server not available\x1b[0m\n'
        self.assertEqual(skip_reason(detail), 'mysql server not available')
        self.assertEqual(category('mysql server not available'), 'service')
        self.assertEqual(category('skip on ZTS'), 'zts')
        self.assertEqual(category('not support in nts'), 'zts')
        self.assertEqual(category('for select'), 'other')
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'shard.json'
            report.write_text(json.dumps({'results': [
                {'test': 'tests/a/1.phpt', 'module': 'a', 'status': 'passed', 'upstream_status': 'PASSED'},
                {'test': 'tests/a/2.phpt', 'module': 'a', 'status': 'skipped', 'upstream_status': 'SKIPPED', 'detail': detail},
                {'test': 'tests/b/1.phpt', 'module': 'b', 'status': 'failed', 'upstream_status': 'WARNED'}]}))
            results = list(rows([report]))
        self.assertEqual([r['status'] for r in results], ['passed', 'skipped', 'failed'])
        self.assertIn('1 passed, 1 failed, 1 skipped', markdown(results))
        self.assertIn('| a | 1 | 0 | 1 |', markdown(results))


if __name__ == '__main__':
    unittest.main()
