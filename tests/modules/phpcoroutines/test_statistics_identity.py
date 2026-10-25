import unittest
from stats_runtime import validate_projection


class StatisticsIdentity(unittest.TestCase):
    def test_qualified_source_and_real_caller(self):
        validate_projection({'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/stats.rs': 'qualified'}}},
                            b'+        const auto plan = swr_v1_phpcoroutines_stats(&state, observation, has_iouring);\n', 'qualified')

    def test_old_feature_bit_without_stats_source_rejected(self):
        with self.assertRaises(ValueError):
            validate_projection({'inputs': {'rust_sources_sha256': {}}}, b'', 'qualified')

    def test_native_caller_or_changed_rust_rejected(self):
        for digest, patch in [('qualified', b'original native body'), ('different', b'')]:
            with self.assertRaises(ValueError):
                validate_projection({'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/stats.rs': digest}}}, patch, 'qualified')
