"""benchmarks/callgrind.py's ratchet: a recorded ratio may drift by noise, no more."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks import callgrind  # noqa: E402


class Ratchet(unittest.TestCase):
    def test_within_noise_passes(self):
        self.assertEqual(callgrind.verdict(1.205, recorded=1.20)[1:], (False, False))

    def test_above_noise_fails(self):
        self.assertTrue(callgrind.verdict(1.22, recorded=1.20)[1])

    def test_beating_the_record_asks_to_lower_it(self):
        self.assertEqual(callgrind.verdict(1.17, recorded=1.20)[1:], (False, True))

    def test_recorded_ratio_overrides_max_ratio(self):
        self.assertFalse(callgrind.verdict(1.10, recorded=1.10, max_ratio=1.05)[1])
        self.assertTrue(callgrind.verdict(1.10, max_ratio=1.05)[1])

    def test_every_merge_tier_workload_is_recorded(self):
        limits = json.loads((ROOT / 'benchmarks/callgrind_limits.json').read_text())
        workflow = (ROOT / '.github/workflows/merge.yml').read_text()
        gated = {w for w in callgrind.WORKLOADS if f'--workload {w} ' in workflow or f'--workload {w}\n' in workflow}
        self.assertEqual(gated, set(limits))


if __name__ == '__main__':
    unittest.main()
