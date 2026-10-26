"""Original Scheduler state publication points and native allocation custody."""
import os
from pathlib import Path
import unittest
from overlay import body, selected


class SchedulerPhaseBoundary(unittest.TestCase):
    def test_original_allocation_and_publication_points(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine_scheduler.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        overlay = selected(original)
        create = 'static zend_object *scheduler_create_object(zend_class_entry *ce) {'
        self.assertEqual(body(original, create), body(overlay, create))
        self.assertIn('zend_object_alloc(sizeof(SchedulerObject), ce)', body(overlay, create))
        for method in ['add', 'parallel', 'start']:
            signature = 'static PHP_METHOD(swoole_coroutine_scheduler, ' + method + ') {'
            before, after = body(original, signature), body(overlay, signature)
            self.assertEqual(after.split('#else\n', 1)[1].rsplit('#endif', 1)[0], before)
            active = after.split('#else\n', 1)[0]
            self.assertNotIn('if (s->started)', active)
            admission = active.index('SWR_CORO_SCHED_PHASE_READ')
            first_effect = active.index('php_swoole_reactor_init()') if method == 'start' else active.index('ecalloc(')
            self.assertLess(admission, first_effect)
            if method == 'start':
                # Preserve the sticky started=true no-task outcome and publish
                # false only after native event wait/list custody is complete.
                self.assertLess(active.index('php_swoole_reactor_init()'), active.index('SWR_CORO_SCHED_PHASE_START'))
                self.assertLess(active.index('SWR_CORO_SCHED_PHASE_START'), active.index('if (next_kind == SWR_CORO_SCHED_SLOT_ABSENT)'))
                self.assertLess(active.index('php_swoole_event_wait();'), active.index('swr_v1_phpcoroutines_scheduler_drop_slot(&s->list);'))
                self.assertLess(active.index('swr_v1_phpcoroutines_scheduler_drop_slot(&s->list);'), active.index('SWR_CORO_SCHED_PHASE_STOP'))


if __name__ == '__main__':
    unittest.main()
