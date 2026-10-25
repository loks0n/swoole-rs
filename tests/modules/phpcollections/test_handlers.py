"""Collection-only supplemental selection stays exact and fails closed."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('collection_handlers', Path(__file__).with_name('handlers.py'))
handlers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handlers)


class OriginalHandlerInventory(unittest.TestCase):
    def source(self):
        return dict(tests=[dict(path=path, sha256='exact-' + path) for path in reversed(handlers.CASES)] +
                    [dict(path='tests/swoole_global/serialize_deny.phpt', sha256='mixed-not-selected')],
                    support_files=[dict(path='tests/include/bootstrap.php', sha256='original-support')],
                    inventory=dict(cases=4, tree='pinned-tree'), commit=handlers.PIN)

    def test_exact_collection_only_cases_keep_original_hashes_and_support(self):
        source = self.source()
        before = copy.deepcopy(source)
        with patch.object(handlers, 'inventory', return_value=source):
            actual = handlers.manifest(Path('/unused'))
        self.assertEqual([row['path'] for row in actual['tests']], list(handlers.CASES))
        self.assertEqual(actual['support_files'], before['support_files'])
        self.assertEqual({row['path']: row['sha256'] for row in actual['tests']},
                         {row['path']: row['sha256'] for row in before['tests'] if row['path'] in handlers.CASES})
        self.assertIn('not full swoole_global', actual['inventory']['selection'])

    def test_missing_original_refuses_instead_of_narrowing_selection(self):
        source = self.source()
        source['tests'] = source['tests'][1:]
        with patch.object(handlers, 'inventory', return_value=source):
            with self.assertRaisesRegex(ValueError, 'original missing'):
                handlers.manifest(Path('/unused'))


if __name__ == '__main__':
    unittest.main()
