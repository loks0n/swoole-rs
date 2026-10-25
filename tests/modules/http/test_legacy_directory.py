#!/usr/bin/env python3
"""Compiler-free declaration/layout parser controls for the actual SDK gate."""
import unittest
from directory_compat import legacy_fields
from rewrite_store_compat import record_layout, server_layout


class DirectorySourceProof(unittest.TestCase):
    def test_only_exact_default_branch_is_projected(self):
        before='class StaticHandler {\n    std::set<std::string> dir_files;\n  public:\n};'
        after=before.replace('    std::set<std::string> dir_files;', '''#if defined(SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE) && SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE
    LegacyDirectory dir_files;
#else
    std::set<std::string> dir_files;
#endif''')
        self.assertEqual(legacy_fields(before),legacy_fields(after))
        self.assertNotEqual(legacy_fields(before),legacy_fields(after.replace('std::set<std::string> dir_files','std::vector<std::string> dir_files')))
        self.assertNotEqual(legacy_fields(before),legacy_fields(after.replace('  public:','    int extra;\n  public:')))

    def test_all_direct_offsets_and_geometry_remain_material(self):
        native='''*** Dumping AST Record Layout
         0 | class swoole::http_server::StaticHandler
         0 |   Server * serv
         8 |   class std::set<std::string> dir_files
         8 |     void * tree
        32 |   int status_code
           | [sizeof=40, dsize=36, align=8,
           |  nvsize=36, nvalign=8]
'''
        owned=native.replace('class std::set<std::string> dir_files','class LegacyDirectory dir_files')
        def layout(value):return record_layout(value,'swoole::http_server::StaticHandler',{'dir_files':'PRIVATE_DIRECTORY_FIELD'})
        self.assertEqual(layout(native),layout(owned))
        self.assertNotEqual(layout(native),layout(owned.replace('32 |   int status_code','36 |   int status_code')))
        self.assertNotEqual(layout(native),layout(owned.replace('sizeof=40','sizeof=48')))
        with self.assertRaises(ValueError):layout(owned.replace('swoole::http_server::StaticHandler','other::StaticHandler'))
        with self.assertRaises(ValueError):layout('')

    def test_existing_server_normalization_is_unchanged(self):
        output='''*** Dumping AST Record Layout
         0 | class swoole::Server
         0 |   void * other
         8 |   class std::shared_ptr rewrite_rules
           | [sizeof=24, dsize=24, align=8,
           |  nvsize=24, nvalign=8]
'''
        self.assertEqual(server_layout(output),server_layout(output.replace('class std::shared_ptr rewrite_rules','class RewriteRules rewrite_rules')))
        self.assertEqual(server_layout(output)['fields'][0],[0,'void * other'])


if __name__=='__main__':unittest.main()
