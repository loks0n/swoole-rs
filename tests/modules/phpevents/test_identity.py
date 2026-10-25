"""Pure temporal identity checks; no PHP, Event operation, native build or IPC."""
import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from descriptor_runtime import require_callers
from sdk import check_imports


class CallerIdentity(unittest.TestCase):
    def check_source(self, source, **changes):
        row = dict(path='migration/patches/phpevents/event.patch',
                   upstream_paths=['ext-src/swoole_event.cc'],
                   sha256=hashlib.sha256(source).hexdigest())
        row.update(changes)
        return require_callers([row], lambda _: source)

    def test_current_caller_set(self):
        source = b'+ swr_v1_phpevents_alias(index, out);\n+ swr_v1_phpevents_fd(phase, kind, sockets, value);\n+ swr_v1_phpevents_stream(phase, resource, sockets, value);\n+ swr_v1_phpevents_query(phase, events, value);\n'
        self.assertTrue(all(self.check_source(source)['matched'].values()))

    def test_sole_catalogue_caller_accepted(self):
        source = b'+ swr_v1_phpevents_catalogue(index, 0, 1, 2, out);\n+ swr_v1_phpevents_fd(phase, kind, sockets, value);\n+ swr_v1_phpevents_stream(phase, resource, sockets, value);\n+ swr_v1_phpevents_query(phase, events, value);\n'
        self.assertTrue(all(self.check_source(source)['matched'].values()))

    def test_same_bit_older_profile_refused(self):
        source = b'+ swr_v1_phpevents_alias(index, out);\n+ swr_v1_phpevents_fd(phase, kind, sockets, value);\n- swr_v1_phpevents_stream(phase, resource, sockets, value);\n swr_v1_phpevents_query(phase, events, value);\n'
        with self.assertRaisesRegex(ValueError, 'stream, passive_query'):
            self.check_source(source)

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

    def test_checksum_and_destination_not_waived(self):
        with self.assertRaisesRegex(ValueError, 'source differs'):
            self.check_source(b'+ caller();', sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'isolated'):
            self.check_source(b'+ caller();', upstream_paths=['ext-src/swoole_event.cc', 'other.cc'])


if __name__ == '__main__':
    unittest.main()
