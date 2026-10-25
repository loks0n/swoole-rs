"""Compiler-free controls for complete Server layout proof normalization."""
import unittest
import subprocess
import tempfile
import sys
from pathlib import Path
from rewrite_store_compat import server_layout, declaration_order


class LayoutProof(unittest.TestCase):
    def layout(self, field='class std::shared_ptr<class std::vector<Rule> > rewrite_rules', lock=56):
        return '''*** Dumping AST Record Layout
         0 | class other::Server
         0 |   int unrelated
           | [sizeof=4, dsize=4, align=4,
           |  nvsize=4, nvalign=4]
*** Dumping AST Record Layout
         0 | class swoole::Server
         0 |   int first
        40 |   '''+field+'''
        40 |     void * nested_not_a_direct_field
        '''+str(lock)+''' |   class std::mutex lock_
           | [sizeof=96, dsize=96, align=8,
           |  nvsize=96, nvalign=8]
'''

    def test_only_the_granted_private_field_type_is_normalized(self):
        baseline = server_layout(self.layout())
        self.assertEqual(baseline, server_layout(self.layout('class swoole::http_server::RewriteRules rewrite_rules')))
        self.assertEqual(baseline['fields'], [[0, 'int first'], [40, 'PRIVATE_REWRITE_FIELD rewrite_rules'], [56, 'class std::mutex lock_']])
        self.assertNotEqual(baseline, server_layout(self.layout(lock=64)))
        self.assertNotEqual(baseline, server_layout(self.layout().replace('int first', 'long first')))
        self.assertNotEqual(baseline, server_layout(self.layout().replace('sizeof=96', 'sizeof=104')))

    def test_declaration_order_ignores_another_class_mutex(self):
        header="class Earlier { std::mutex lock_; };\n    std::string document_root;\n    http_server::RewriteRules rewrite_rules;\n    std::mutex lock_;"
        self.assertTrue(declaration_order(header))
        self.assertFalse(declaration_order(header.replace('    std::mutex lock_;', '')))
        self.assertFalse(declaration_order(header.replace('    http_server::RewriteRules rewrite_rules;\n    std::mutex lock_;','    std::mutex lock_;\n    http_server::RewriteRules rewrite_rules;')))

    def test_existing_prepared_bytes_are_refused_before_source_or_compiler_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary=Path(temporary)/'prepared';binary.write_bytes(b'immutable')
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('rewrite_store_gate.py')),
                '--source',str(Path(temporary)/'absent-source'),'--archive',str(Path(temporary)/'absent-archive'),
                '--prepare-binary',str(binary),'--output',str(Path(temporary)/'new.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('Refusing existing immutable preparation output',result.stderr)
            self.assertEqual(binary.read_bytes(),b'immutable')
            self.assertFalse((Path(temporary)/'new.json').exists())

    def test_missing_or_other_server_never_infers_layout(self):
        with self.assertRaises(ValueError):
            server_layout(self.layout().replace('swoole::Server', 'another::Server'))
        with self.assertRaises(ValueError):
            server_layout('')


if __name__ == '__main__':
    unittest.main()
