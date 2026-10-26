"""The PHPT gate shards every test once, classifies skips and fails only on upstream passes the hybrid loses."""
import json
from pathlib import Path
import tempfile
import unittest

from corpus.upstream.gate import category, compare, flagged, markdown, recheck, rows, skip_reason
from corpus.upstream.inventory import shard


class PhptGate(unittest.TestCase):
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

    def test_only_upstream_passes_gate_the_hybrid(self):
        def row(test, engine, status):
            return {'test': test, 'family': 'a', 'engine': engine, 'status': status, 'category': 'other'}
        results = [row('kept', 'upstream', 'passed'), row('kept', 'hybrid', 'passed'),
                   row('lost', 'upstream', 'passed'), row('lost', 'hybrid', 'failed'),
                   row('absent', 'upstream', 'passed'),
                   row('both', 'upstream', 'failed'), row('both', 'hybrid', 'failed'),
                   row('fixed', 'upstream', 'failed'), row('fixed', 'hybrid', 'passed'),
                   row('skip', 'upstream', 'skipped'), row('skip', 'hybrid', 'failed')]
        self.assertEqual(compare(results), (['absent (hybrid: missing)', 'lost (hybrid: failed)'], ['both']))
        self.assertEqual(compare([row('only', 'upstream', 'failed')]), ([], []))
        self.assertIn('2 passing on upstream but not here', markdown(results))

    def test_reruns_separate_regressions_from_flakes(self):
        def row(test, engine, status):
            return {'test': test, 'family': 'a', 'engine': engine, 'status': status, 'category': 'other'}
        results = [row(t, 'upstream', 'passed') for t in ['real', 'upstream-flake', 'hybrid-blip', 'unrun', 'kept']]
        results += [row(t, 'hybrid', 'failed') for t in ['real', 'upstream-flake', 'hybrid-blip', 'unrun']]
        results += [row('kept', 'hybrid', 'passed')]
        self.assertEqual(flagged(results), ['hybrid-blip', 'real', 'unrun', 'upstream-flake'])
        rechecked = [row('real', 'upstream', 'passed')] * 3 + [row('real', 'hybrid', 'passed'), row('real', 'hybrid', 'failed')]
        rechecked += [row('upstream-flake', 'upstream', 'failed'), row('upstream-flake', 'hybrid', 'failed')]
        rechecked += [row('hybrid-blip', 'upstream', 'passed'), row('hybrid-blip', 'hybrid', 'passed')]
        # 'unrun' has no re-runs, so it stays a regression.
        self.assertEqual(recheck(flagged(results), rechecked),
                         (['real', 'unrun'], ['upstream-flake'], ['hybrid-blip']))
        summary = markdown(results, rechecked)
        self.assertIn('2 regressions: pass on upstream, fail on a re-run here', summary)
        self.assertIn('1 flaky on upstream', summary)
        self.assertIn('1 passed on re-run on both engines', summary)

    def test_incomplete_shards_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / 'shard.json'
            report.write_text(json.dumps({'execution_status': 'interrupted', 'results': []}))
            with self.assertRaises(ValueError):
                list(rows([report]))


if __name__ == '__main__':
    unittest.main()
