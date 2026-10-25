"""Primitive state custody source proof; no actual context/opcode/observer work."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected, header_selected


class MetadataBoundary(unittest.TestCase):
    def test_initialization_and_native_effect_frontiers(self):
        root = Path(__file__).resolve().parents[3]
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src'))
        if not (pin / 'ext-src/swoole_coroutine.cc').exists():
            self.skipTest('Supply pinned source')
        source = (pin / 'ext-src/swoole_coroutine.cc').read_text()
        selected = coroutine_selected(source)
        for signature in ['static int coro_begin_silence_handler(zend_execute_data *execute_data) {',
                          'static int coro_end_silence_handler(zend_execute_data *execute_data) {',
                          'PHPContext *PHPCoroutine::create_context(const Args *args) {']:
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'
            self.assertTrue(after.endswith(suffix))
            active = after[:-len(suffix)]
            self.assertIn('swr_v1_phpcoroutines_metadata(', active)
            if 'create_context(' in signature:
                self.assertIn('ctx->in_silence = {0};', active)
                self.assertIn('ctx->fiber_init_notified = {0};', active)
                self.assertIn('SWR_CORO_METADATA_INIT_SCHEDULER', active)
                self.assertIn('SWR_CORO_METADATA_SET_PARENT', active)
                self.assertNotIn('ctx->pcid =', active)
                self.assertNotIn('ctx->enable_scheduler =', active)
                # All unallocated Zend/VM allocation and setup statements stay
                # byte-for-byte, not a mirror or an alternate allocation path.
                for line in before.splitlines():
                    statement = line.strip()
                    if statement.startswith(('EG(', 'ZVAL_', 'Z_', 'zend_', 'ctx->co', 'ctx->co->', 'memset(')):
                        self.assertIn(statement, active)
            else:
                self.assertEqual(active.count('PHPCoroutine::get_context()'), 1)
                self.assertNotIn('task->in_silence =', active)
                self.assertIn('return ZEND_USER_OPCODE_DISPATCH;', active)
        h = (pin / 'ext-src/php_swoole_coroutine.h').read_text()
        hs = header_selected(h)
        reset = 'static inline void free_main_context() {'
        self.assertEqual(body(h, reset), body(hs, reset))
        init = body(hs, 'static inline void init_main_context() {').split('#else', 1)[0]
        self.assertIn('main_context.co = nullptr;', init)
        self.assertIn('main_context.fiber_context = EG(main_fiber_context);', init)
        self.assertIn('SWR_CORO_METADATA_INIT_FIBER', init)
        self.assertIn('save_context(&main_context);', init)


if __name__ == '__main__':
    unittest.main()
