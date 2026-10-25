"""Regression: accepted ABI2 layout differs while behavior remains identical."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from storage_summary import compare


class SummaryTests(unittest.TestCase):
    def fixture(self):
        # Exact summaries from frozen0656's first failed Linux production run.
        common = dict(level_cases=11, filename_cases=54, reopen_records=2,
                      caller_streams=2, thread_records=1024, thread_reopens=64)
        layouts = dict(hybrid=dict(sizeof_logger=72, alignof_logger=8),
                       upstream=dict(sizeof_logger=184, alignof_logger=8))
        return [dict(engine=name, summary={**common, **layout}) for name, layout in layouts.items()], layouts

    def test_accepted_layouts_keep_all_behavior_comparisons(self):
        rows, layouts = self.fixture()
        compare(rows, layouts)
        for key in ['level_cases', 'filename_cases', 'reopen_records', 'caller_streams', 'thread_records', 'thread_reopens']:
            bad = copy.deepcopy(rows)
            bad[0]['summary'][key] -= 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'summaries differ'):
                compare(bad, layouts)

        for key, value in dict(configuration_formats=10, configuration_accepted=7,
                               configuration_rejected=3, configuration_resets=32).items():
            extended = copy.deepcopy(rows)
            for row in extended:
                row['summary'][key] = value
            compare(extended, layouts)
            extended[0]['summary'][key] -= 1
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'summaries differ'):
                compare(extended, layouts)

    def test_wrong_helper_layout_still_fails(self):
        rows, layouts = self.fixture()
        for key in ['sizeof_logger', 'alignof_logger']:
            bad = copy.deepcopy(rows)
            bad[0]['summary'][key] += 8
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'differs from its engine SDK'):
                compare(bad, layouts)

    def test_other_profiles_retain_full_summary_equality(self):
        with self.assertRaisesRegex(ValueError, 'summaries differ'):
            compare([dict(summary=dict(records=3)), dict(summary=dict(records=2))])


if __name__ == '__main__':
    unittest.main()
