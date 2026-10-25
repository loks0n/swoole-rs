"""Source-only exit policy/effect custody; no exit/opcode/exception execution."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected
from exit_bodies import SIGNATURES


class ExitBoundary(unittest.TestCase):
    def test_exact_fallback_and_native_payload_contract(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        overlay = coroutine_selected(original)
        for signature in SIGNATURES:
            before, after = body(original, signature), body(overlay, signature)
            # Nested EX_CONSTANT preprocessor alternatives exist in both
            # branches. Match the exact outer fallback suffix instead.
            suffix = '#else' + before + '#endif\n'
            self.assertTrue(after.endswith(suffix))
            active = after[:-len(suffix)]
            self.assertNotIn('zend_long flags', active)
            self.assertNotIn('flags |=', active)
            for call in ['Coroutine::get_current()', 'sw_server() != nullptr', 'sw_server()->is_started()']:
                self.assertEqual(active.count(call), 1)
            self.assertIn('SW_EXIT_IN_COROUTINE, SW_EXIT_IN_SERVER, IS_UNUSED, IS_CONST', active)
            self.assertIn('swr_v1_phpcoroutines_exit(&state, &config,', active)
            self.assertIn('ZVAL_OBJ(&ex, obj);', active)
            self.assertIn('zend_update_property_long(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("flags"), part.flags);', active)
            if 'coro_exit_handler' in signature:
                self.assertIn(body(before, 'if (opline->op1_type == IS_CONST) {'), active)
                for statement in ['exit_status = EX_VAR(opline->op1.var);', 'exit_status = Z_REFVAL_P(exit_status);',
                                  'ZVAL_DUP(&_exit_status, exit_status);', 'Z_TRY_ADDREF_P(exit_status);',
                                  'zend_update_property(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("status"), exit_status);']:
                    self.assertIn(statement, active)
            else:
                for statement in ['Z_PARAM_STR_OR_LONG(message, status)',
                                  'php_swoole_call_original_handler(ZEND_STRL("exit"), INTERNAL_FUNCTION_PARAM_PASSTHRU)',
                                  'php_write(ZSTR_VAL(message), ZSTR_LEN(message));', 'sw_php_exit(status);']:
                    self.assertIn(statement, active)


if __name__ == '__main__':
    unittest.main()
