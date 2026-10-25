"""Source census must account for bodies without treating comments as calls."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location('collection_body_map', Path(__file__).with_name('body_map.py'))
body_map = importlib.util.module_from_spec(spec)
spec.loader.exec_module(body_map)


class BodyAccounting(unittest.TestCase):
    def test_nested_braces_strings_and_comments_do_not_truncate_bodies(self):
        text = '''static void example() {
    const char *x = "} swr_v1_phpcollections_fake(";
    /* } */ if (true) { native(); }
}
'''
        result = body_map.account(text, text, {'example': 'native'})
        self.assertEqual(result['functions'][0]['original']['lines'], [1, 4])
        self.assertEqual(result['functions'][0]['direct_rust_exports'], [])
        self.assertFalse(result['functions'][0]['whole_function_replaced_by_rust'])

    def test_unknown_or_missing_function_fails_closed(self):
        text = 'void example() { native(); }\n'
        for selected in ['', text + 'void unknown() { native(); }\n']:
            with self.assertRaisesRegex(ValueError, 'boundary review'):
                body_map.account(text, selected, {'example': 'native'})

    def test_declared_added_bridge_must_exist_and_resolve_lexical_exports(self):
        original = 'void example() { native(); }\n'
        selected = 'void bridge() { swr_v1_phpcollections_count(0, 1, 2); }\nvoid example() { bridge(); }\n'
        result = body_map.account(original, selected, {'example': 'native'}, {'bridge': 'shared native bridge'})
        self.assertEqual(result['functions'][0]['reachable_local_helper_exports'], ['swr_v1_phpcollections_count'])
        self.assertEqual(result['functions'][0]['direct_rust_exports'], [])
        with self.assertRaisesRegex(ValueError, 'boundary review'):
            body_map.account(original, original, {'example': 'native'}, {'bridge': 'shared native bridge'})

    def test_macro_method_identity_and_unbalanced_source(self):
        self.assertEqual(list(body_map.functions('static PHP_METHOD(collection, pop) { native(); }\n')), ['collection::pop'])
        with self.assertRaisesRegex(ValueError, 'Unbalanced'):
            body_map.functions('void example() { native();\n')


if __name__ == '__main__':
    unittest.main()
