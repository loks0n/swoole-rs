"""Appwrite e2e reports gate only tests that pass on stock Swoole."""
from pathlib import Path
import tempfile
import unittest

from tools.appwrite_e2e import compare, load


def junit(cases):
    body = ''.join(f'<testcase class="T" name="{name}">{"<failure/>" if outcome == "failed" else ""}'
                   f'{"<skipped/>" if outcome == "skipped" else ""}</testcase>'
                   for name, outcome in cases.items())
    return f'<testsuites><testsuite name="s">{body}</testsuite></testsuites>'


class CompareTest(unittest.TestCase):
    def reports(self, upstream, hybrid):
        directory = Path(tempfile.mkdtemp())
        for variant, services in [('upstream', upstream), ('hybrid', hybrid)]:
            for service, cases in services.items():
                path = directory / f'junit-{variant}-{service}' / 'junit.xml'
                path.parent.mkdir()
                path.write_text(junit(cases))
        return compare(load(directory))

    def test_regression_is_a_stock_pass_that_fails_or_vanishes(self):
        regressions, flaky, missing, counts = self.reports(
            {'Account': {'a': 'passed', 'b': 'passed', 'c': 'failed', 'd': 'skipped'}},
            {'Account': {'a': 'passed', 'b': 'failed', 'c': 'failed', 'd': 'failed'}})
        self.assertEqual(regressions, ['Account: T::b (failed)'])
        self.assertEqual(flaky, ['Account: T::c'])
        self.assertEqual((missing, counts), ([], {'Account': (2, 1)}))
        regressions, *_ = self.reports({'Account': {'a': 'passed'}}, {'Account': {}})
        self.assertEqual(regressions, ['Account: T::a (missing)'])

    def test_service_without_hybrid_report_is_missing(self):
        _, _, missing, _ = self.reports({'Account': {'a': 'passed'}, 'Teams': {'a': 'passed'}},
                                        {'Account': {'a': 'passed'}})
        self.assertEqual(missing, ['Teams'])


if __name__ == '__main__':
    unittest.main()
