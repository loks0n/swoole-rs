"""Pure identity validation, no archive execution, PHP or native fault profiles."""
import unittest
from gate import validate_abi


class ArchiveIdentityTests(unittest.TestCase):
    def test_module_and_combined_archives(self):
        validate_abi({'abi': 1, 'bits': 134217728})
        validate_abi({'abi': 1, 'bits': 268435455})

    def test_missing_feature_refused(self):
        with self.assertRaisesRegex(ValueError, 'feature bit'):
            validate_abi({'abi': 1, 'bits': 67108864})

    def test_wrong_version_refused(self):
        with self.assertRaisesRegex(ValueError, 'ABI version'):
            validate_abi({'abi': 2, 'bits': 134217728})

    def test_malformed_unsigned_identity_refused(self):
        for bits in (-1, True, '134217728', 1 << 64):
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                validate_abi({'abi': 1, 'bits': bits})
