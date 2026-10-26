"""Source-only cancellation/timer custody; no actual effects or stopped profiles."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from control_bodies import SIGNATURES


class ControlBoundary(unittest.TestCase):
    def test_exact_fallback_native_exception_and_timer_effect_order(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        if not (pin / 'ext-src/swoole_coroutine.cc').exists():
            self.skipTest('Supply pinned source')
        source = (pin / 'ext-src/swoole_coroutine.cc').read_text()
        selected = coroutine_selected(source)
        active = []
        for signature in SIGNATURES:
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'
            self.assertTrue(after.endswith(suffix))
            current = after[:-len(suffix)]
            self.assertIn('swr_v1_phpcoroutines_control(', current)
            self.assertNotIn('swr_v1_phpcoroutines_control(task', current)
            self.assertNotIn('swr_v1_phpcoroutines_control(co', current)
            active.append(current)
        cancellation, timer = active
        effects = ['exception = zend_objects_new(ce);', 'object_properties_init(exception, ce);',
                   'zend_throw_exception_object(&zexception);',
                   'previous = task->exception;', 'task->exception_class = ce;', 'task->exception = exception;',
                   'zend_exception_set_previous(exception, previous);',
                   'ex_backup = EG(current_execute_data);', 'EG(current_execute_data) = task->execute_data;',
                   'EG(current_execute_data) = ex_backup;',
                   'task->opline_before_exception = task->execute_data->opline;',
                   'task->execute_data->opline = EG(exception_op);', 'task->co->cancel();']
        positions = [cancellation.index(statement) for statement in effects]
        self.assertEqual(positions, sorted(positions))
        for statement in effects:
            self.assertEqual(cancellation.count(statement), 1)
        before = body(source, SIGNATURES[1])
        self.assertIn(before[:before.index('    if (sw_unlikely(timeout <= 0 || co == nullptr)) {')], timer)
        self.assertIn('swoole_timer_add(timeout, false, [cid]', timer)
        self.assertLess(timer.index('PHPCoroutine::get_context_by_cid(cid);'), timer.index('ctx->timer_limit = nullptr;'))
        self.assertLess(timer.index('ctx->timer_limit = nullptr;'),
                        timer.index('php_swoole_coroutine_throw_exception(cid, true, swoole_coroutine_timeout_exception_ce);'))
        self.assertEqual(timer.count('php_swoole_coroutine_throw_exception(cid, true, swoole_coroutine_timeout_exception_ce);'), 1)
        self.assertLess(timer.index('ctx->timer_limit = timer;'), timer.index('swoole_timer_del(old);'))
        # Core registry iteration remains Native, rather than a duplicate list.
        signature = 'static PHP_METHOD(swoole_coroutine, list) {'
        self.assertEqual(body(source, signature), body(selected, signature))


if __name__ == '__main__':
    unittest.main()
