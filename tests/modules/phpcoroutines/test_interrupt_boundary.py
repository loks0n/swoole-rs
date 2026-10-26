"""Source-only interrupt ordering and Native effect custody, no interruption."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected


class InterruptBoundary(unittest.TestCase):
    def test_native_effects_short_circuit_and_fallback(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        overlay = coroutine_selected(original)
        for signature, prefix, effects, observations in [
            ('static void coro_interrupt_resume(void *data) {', 'auto *co = static_cast<Coroutine *>(data);',
             ['swoole_trace_log(SW_TRACE_COROUTINE, "interrupt_callback cid=%ld ", co->get_cid());', 'co->resume();'],
             ['co != nullptr', 'co->is_end()']),
            ('static void coro_interrupt_function(zend_execute_data *execute_data) {',
             'PHPContext *task = PHPCoroutine::get_context();',
             ['swoole_event_defer(coro_interrupt_resume, (void *) task->co);', 'task->co->yield();',
              'orig_interrupt_function(execute_data);'],
             ['task != nullptr', 'task->co != nullptr', 'PHPCoroutine::is_schedulable(task)',
              'orig_interrupt_function != nullptr']),
        ]:
            before, after = body(original, signature), body(overlay, signature)
            active, fallback = after.split('#else', 1)
            self.assertEqual(fallback.rsplit('#endif', 1)[0], before)
            self.assertEqual(active.count(prefix), 1)
            for statement in effects:
                self.assertIn(statement, before)
                self.assertEqual(active.count(statement), 1)
            for expression in observations:
                self.assertIn('observation = ' + expression + ';', active)
            self.assertIn('swr_coro_transfer_next(&stage,', active)
            self.assertNotIn('swr_coro_transfer_next(task', active)
            self.assertNotIn('swr_coro_transfer_next(co', active)


if __name__ == '__main__':
    unittest.main()
