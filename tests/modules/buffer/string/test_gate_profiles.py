"""String gate profile selection and ownership inventory checks; no build."""
import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('string_gate',Path(__file__).with_name('gate.py'))
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
class GateProfiles(unittest.TestCase):
    def test_ownership_profile_rejects_truncated_or_wrong_origin_inventory(self):
        self.assertTrue(gate.ownership_inventory({'checks':13,'selected_origin_checks':0},False))
        self.assertTrue(gate.ownership_inventory({'checks':13,'selected_origin_checks':3},True))
        for row in [{}, {'checks':0,'selected_origin_checks':0}, {'checks':13,'selected_origin_checks':0}]:
            self.assertFalse(gate.ownership_inventory(row,True))

    def test_ownership_and_transition_are_mutually_exclusive(self):
        argv=['gate.py','--source','/missing','--archive','/missing','--ownership-only','--transition-only']
        with patch('sys.argv',argv),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:gate.main()
        self.assertEqual(raised.exception.code,2)

    def test_allocation_and_ownership_are_mutually_exclusive(self):
        argv=['gate.py','--source','/missing','--archive','/missing','--allocation-only','--ownership-only']
        with patch('sys.argv',argv),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:gate.main()
        self.assertEqual(raised.exception.code,2)

    def test_format_and_allocation_are_mutually_exclusive(self):
        argv=['gate.py','--source','/missing','--archive','/missing','--format-only','--allocation-only']
        with patch('sys.argv',argv),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:gate.main()
        self.assertEqual(raised.exception.code,2)

    def test_random_and_format_are_mutually_exclusive(self):
        argv=['gate.py','--source','/missing','--archive','/missing','--random-only','--format-only']
        with patch('sys.argv',argv),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:gate.main()
        self.assertEqual(raised.exception.code,2)
if __name__=='__main__':unittest.main()
