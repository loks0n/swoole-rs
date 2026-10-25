"""Private config storage proof cannot accept old production bits or missing callers."""
import unittest
from stats_runtime import validate_config_projection, CONFIG_HEADER_MARKERS, CONFIG_CPP_MARKERS


class ConfigIdentity(unittest.TestCase):
    def test_requires_compiled_state_and_all_native_points(self):
        manifest = {'inputs': {'rust_sources_sha256': {'crates/phpcoroutines/src/config_state.rs': 'qualified'}}}
        patch, header = b'\n'.join(CONFIG_CPP_MARKERS), b'\n'.join(CONFIG_HEADER_MARKERS)
        validate_config_projection(manifest, patch, header, 'qualified')
        with self.assertRaises(ValueError):
            validate_config_projection(manifest, patch, header, 'old')
        for missing in CONFIG_HEADER_MARKERS:
            with self.assertRaises(ValueError):
                validate_config_projection(manifest, patch, header.replace(missing, b''), 'qualified')
        for missing in CONFIG_CPP_MARKERS:
            with self.assertRaises(ValueError):
                validate_config_projection(manifest, patch.replace(missing, b''), header, 'qualified')


if __name__ == '__main__':
    unittest.main()
