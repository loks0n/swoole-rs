"""Definition selection fixtures, with no package downloads/native execution."""
import unittest
from gnu_source_body import definition


class GnuSourceDefinitions(unittest.TestCase):
    def test_declaration_cannot_select_later_unrelated_brace(self):
        text='void rehash(int n);\nvoid unrelated(){wrong();}\nvoid rehash(int n) {right();}'
        self.assertEqual(definition(text,r'void rehash\(int n\)'),'{right();}')

    def test_duplicate_missing_and_unterminated_definition_refuse(self):
        for text in ['void f(); void unrelated() {}','void f() {} void f() {}','void f() {']:
            with self.subTest(text=text), self.assertRaises(ValueError):definition(text,r'void f\(\)')

    def test_definition_suffix_disambiguates_gnu_declaration(self):
        text='_M_rehash_aux(size_type n, true_type keys); void wrong() {}\n_M_rehash_aux(size_type n, true_type /* keys */) { correct(); }'
        self.assertEqual(definition(text,r'_M_rehash_aux\(size_type n, true_type /\* keys \*/\)'),'{ correct(); }')


if __name__=='__main__':unittest.main()
