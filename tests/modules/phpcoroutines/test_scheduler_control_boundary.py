"""Source-only remaining Scheduler control; no callbacks/shutdown/destruction."""
import os
from pathlib import Path
import unittest
from overlay import body, selected
from scheduler_control_bodies import SIGNATURES


class SchedulerControlBoundary(unittest.TestCase):
    def test_native_fallback_and_required_external_effects(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        path = pin / 'ext-src/swoole_coroutine_scheduler.cc'
        if not path.exists():
            self.skipTest('Supply pinned source')
        source = path.read_text()
        overlay = selected(source)
        active = []
        for signature in SIGNATURES:
            before, after = body(source, signature), body(overlay, signature)
            suffix = '#else' + before + '#endif\n'
            self.assertTrue(after.endswith(suffix))
            current = after[:-len(suffix)]
            self.assertIn('swr_v1_phpcoroutines_' + ('scheduler_control(' if 'getOptions' in signature else 'callback_control('), current)
            active.append(current)
        callback, shutdown, options = active
        for statement in ['SW_ASSERT(plan.identity);', 'ZVAL_NULL(&retval);',
                          'sw_zend_call_function_ex(nullptr, reinterpret_cast<zend::Callable *>(plan.identity)->ptr(), 0, nullptr, &retval);',
                          'php_swoole_fatal_error(E_ERROR, "Coroutine can_exit callback handler error");',
                          'zend_exception_error(EG(exception), E_ERROR);']:
            self.assertEqual(callback.count(statement), 1)
        self.assertLess(callback.index('SW_ASSERT('), callback.index('ZVAL_NULL('))
        self.assertLess(callback.index('ZVAL_NULL('), callback.index('case SWR_CORO_SCHED_CONTROL_CALL:'))
        self.assertIn('observation = EG(exception) != nullptr;', callback)
        self.assertIn('observation = Z_TYPE_P(&retval);', callback)
        for statement in ['zval_dtor((zval *) iter->private_data);', 'efree(iter->private_data);',
                          'return SW_TRAVERSE_KEEP;', 'return SW_TRAVERSE_REMOVE;',
                          'sw_callable_free(reinterpret_cast<zend::Callable *>(plan.identity));']:
            self.assertEqual(shutdown.count(statement), 1)
        self.assertIn('const int64_t type = iter->type;', shutdown)
        self.assertLess(shutdown.index('zval_dtor('), shutdown.index('efree('))
        self.assertNotIn('exit_condition_fci_cache =', shutdown)
        self.assertNotIn('exit_condition_fci_cache !=', shutdown)
        self.assertIn('static swr_phpcoroutines_scheduler_callback_owner exit_condition_fci_cache{0};', overlay)
        self.assertIn('#else\nstatic zend::Callable *exit_condition_fci_cache = nullptr;\n#endif', overlay)
        self.assertIn('RETURN_ARR(zend_array_dup(PHPCoroutine::options));', options)
        self.assertIn('observation = PHPCoroutine::options != nullptr;', options)

    def test_complete_callback_identity_has_no_native_owner_mirror(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        path = pin / 'ext-src/swoole_coroutine_scheduler.cc'
        if not path.exists():
            self.skipTest('Supply pinned source')
        source = path.read_text()
        overlay = selected(source)
        declaration = 'static swr_phpcoroutines_scheduler_callback_owner exit_condition_fci_cache{0};'
        self.assertEqual(overlay.count(declaration), 1)
        self.assertNotIn('SW_THREAD_LOCAL ' + declaration, overlay)
        for signature in SIGNATURES[:2] + ['PHP_METHOD(swoole_coroutine_scheduler, set) {']:
            original = body(source, signature)
            current = body(overlay, signature)
            marker = '#else' + original + '#endif' if 'set)' not in signature else '#else\n' + original + '#endif'
            self.assertIn(marker, current)
            active = current[:current.index(marker)]
            for native_owner in ['exit_condition_fci_cache->', 'exit_condition_fci_cache =',
                                 'exit_condition_fci_cache !=', 'sw_callable_free(exit_condition_fci_cache)']:
                self.assertNotIn(native_owner, active)
        configured = body(overlay, 'PHP_METHOD(swoole_coroutine_scheduler, set) {').split('#else\n', 1)[0]
        self.assertIn('swr_v1_phpcoroutines_configure_owned(&state, &exit_condition_fci_cache, observation, created)', configured)
        self.assertIn('created = reinterpret_cast<uintptr_t>(sw_callable_create(ztmp));', configured)
        self.assertIn('sw_callable_free(reinterpret_cast<zend::Callable *>(owned.identity));', configured)


if __name__ == '__main__':
    unittest.main()
