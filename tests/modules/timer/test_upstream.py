"""The broad timer selection never drops an original case silently."""
import hashlib
import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('timer_upstream', Path(__file__).with_name('upstream.py'))
suite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(suite)


class Selection(unittest.TestCase):
    def setUp(self):
        self.names = sorted(suite.EXTERNAL) + [f'local_{number:02}' for number in range(29)]
        self.paths = [f'tests/swoole_timer/{name}.phpt' for name in self.names]

    def command(self, args, **kwargs):
        if 'rev-parse' in args:
            return suite.COMMIT
        if 'ls-tree' in args:
            return '\n'.join(self.paths)
        return b'--FILE--\noriginal assertions\n'

    def test_local_gate_accounts_for_all_four_unmeasured_cases(self):
        with patch.object(suite.subprocess, 'check_output', side_effect=self.command):
            cases, omitted = suite.selection(Path('fixture'))
        self.assertEqual(len(cases), 29)
        self.assertEqual({Path(path).stem for path in omitted}, suite.EXTERNAL)
        self.assertEqual(cases[0]['sha256'], hashlib.sha256(self.command([])).hexdigest())

    def test_external_cases_require_explicit_network_selection(self):
        with patch.object(suite.subprocess, 'check_output', side_effect=self.command):
            cases, omitted = suite.selection(Path('fixture'), external=True)
            self.assertEqual((len(cases), omitted), (33, []))
            with self.assertRaisesRegex(ValueError, 'external cases require'):
                suite.selection(Path('fixture'), names=['bug_4794_3'])

    def test_fixed_port_guard_refuses_live_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaises(OSError):
                suite.require_free_port(port)
        suite.require_free_port(port)

    def test_unknown_names_wrong_pin_and_incomplete_inventory_fail(self):
        with patch.object(suite.subprocess, 'check_output', side_effect=self.command):
            with self.assertRaisesRegex(ValueError, 'Unknown'):
                suite.selection(Path('fixture'), names=['not_original'])
            self.paths.pop()
            with self.assertRaisesRegex(ValueError, '33-case'):
                suite.selection(Path('fixture'))
        with patch.object(suite.subprocess, 'check_output', return_value='wrong-pin'):
            with self.assertRaisesRegex(ValueError, 'frozen pin'):
                suite.selection(Path('fixture'))


if __name__ == '__main__':
    unittest.main()
