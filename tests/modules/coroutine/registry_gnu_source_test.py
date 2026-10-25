"""Regression for the observed declaration-versus-definition evidence bug."""
import unittest
from registry_gnu_source import body


class DefinitionBinding(unittest.TestCase):
    def test_skips_declaration_and_unrelated_braces(self):
        text = 'void f(int); struct Other { int value; }; void f(int x) { if (x) { --x; } }'
        self.assertEqual(body(text, 'f(int'), 'f(int x) { if (x) { --x; } }')

    def test_missing_and_ambiguous_definitions_refuse(self):
        for text in ['void f(int); struct Other { int value; };',
                     'void f(int x) {} void f(int y) {}']:
            with self.assertRaises(ValueError):
                body(text, 'f(int')


if __name__ == '__main__':
    unittest.main()
