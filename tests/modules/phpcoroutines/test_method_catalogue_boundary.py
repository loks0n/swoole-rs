"""Whole registration catalogue/projection closure; no Zend or handler execution."""
import os
from pathlib import Path
import unittest
from make_patches import body, selected, coroutine_selected, system_selected
from method_catalogue_bodies import BRIDGE, declarations, bindings, selected_table


class MethodCatalogueBoundary(unittest.TestCase):
    def test_original_tables_and_minit_fallback_are_exact(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        cases = [('swoole_coroutine.cc', coroutine_selected, 'php_swoole_coroutine_minit'),
                 ('swoole_coroutine_scheduler.cc', selected, 'php_swoole_coroutine_scheduler_minit'),
                 ('swoole_coroutine_system.cc', system_selected, 'php_swoole_coroutine_system_minit')]
        counts = []
        for file, transform, name in cases:
            path = pin / 'ext-src' / file
            if not path.exists(): self.skipTest('Supply pinned source')
            original = path.read_text(); current = transform(original)
            self.assertEqual(current.count(BRIDGE), 1)
            sig = 'void ' + name + '(int module_number) {'
            old, new = body(original, sig), body(current, sig)
            fallback = new.rindex('#else\n' + old)
            self.assertEqual(new[fallback + len('#else\n'):].rsplit('#endif', 1)[0], old)
            active = new[:fallback]
            for table in declarations(original):
                self.assertEqual(current.count(selected_table(table)), 1)
                self.assertIn('#else\n' + table[0] + '\n#endif', selected_table(table))
                counts.append(len(bindings(table[2])))
                self.assertIn('php_coroutine_project_methods(', active)
                projection = active.index(table[1] + '_bindings, ' + table[1] + ');')
                publication = active.index('methods = ' + table[1] + ';') if table[1] in ('swoole_coroutine_methods','swoole_exit_exception_methods') else active.index('swr_phpcoroutines_register_class(')
                self.assertLess(projection, publication)
                for condition, binding in bindings(table[2]):
                    self.assertNotIn('"', binding)  # Actual typed addresses/counts, no logical name catalogue.
                    self.assertIn('sizeof(zend_internal_arg_info)', binding)
                    self.assertIn(condition, (None, 'SW_CORO_TIME'))
        self.assertEqual(counts, [38, 2, 5, 12])

    def test_projector_is_only_typed_native_effect_storage(self):
        self.assertLess(BRIDGE.index('swr_v1_phpcoroutines_method('), BRIDGE.index('entry.fname ='))
        self.assertIn('projection[method.slot] = {};', BRIDGE)
        self.assertIn('bindings[method.handler]', BRIDGE)
        for forbidden in ('zend_register_', 'emalloc(', 'new ', 'malloc(', 'static bool', 'reinterpret_cast'):
            self.assertNotIn(forbidden, BRIDGE)


if __name__ == '__main__':
    unittest.main()
