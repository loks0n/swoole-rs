"""sdk.py's object-import checks; no PHP, Event operation, native build or IPC."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from sdk import check_imports


class ImportIdentity(unittest.TestCase):
    def test_native_and_partial_object_imports_refused(self):
        self.assertEqual(check_imports(' U zend_parse_parameters', 'native'), [])
        with self.assertRaisesRegex(ValueError, 'Native profile'):
            check_imports(' U _swr_v1_phpevents_query', 'native')
        with self.assertRaisesRegex(ValueError, 'imports missing'):
            check_imports(' U swr_v1_phpevents_query', 'combined')

    def test_pre_custody_caller_object_refused(self):
        from sdk import EXPORTS
        legacy = EXPORTS - {'swr_v1_phpevents_callbacks', 'swr_v1_phpevents_update_owned'}
        with self.assertRaisesRegex(ValueError, 'callbacks.*update_owned'):
            check_imports('\n'.join(' U ' + name for name in sorted(legacy)), 'combined')
        current = EXPORTS - {'swr_v1_phpevents_update', 'swr_v1_phpevents_alias', 'swr_v1_phpevents_registry_insert'}
        self.assertEqual(check_imports('\n'.join(' U ' + name for name in sorted(current)), 'combined'), sorted(current))


if __name__ == '__main__':
    unittest.main()
