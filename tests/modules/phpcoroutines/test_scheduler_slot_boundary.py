"""Source closure for list-cell custody; no actual Scheduler callbacks/lifetime."""
import os
import re
from pathlib import Path
import unittest
from overlay import body, selected
from scheduler_slot_bodies import ADD, FREE, START


class SchedulerSlotBoundary(unittest.TestCase):
    def test_whole_cell_closure_and_native_effect_order(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        path = pin / 'ext-src/swoole_coroutine_scheduler.cc'
        if not path.exists():
            self.skipTest('Supply pinned source')
        source = path.read_text()
        overlay = selected(source)
        active = {}
        for signature in (FREE, START):
            before, after = body(source, signature), body(overlay, signature)
            self.assertEqual(after.split('#else\n', 1)[1].rsplit('#endif', 1)[0], before)
            active[signature] = after.split('#else\n', 1)[0]
        active[ADD] = body(overlay, ADD)
        for current in active.values():
            self.assertIsNone(re.search(r'(?<!&)\bs->list\b', current))
        add = active[ADD]
        self.assertLess(add.index('scheduler_prepare_slot('), add.index('sw_zend_fci_cache_persist('))
        self.assertLess(add.index('sw_zend_fci_cache_persist('), add.index('sw_zend_fci_params_persist('))
        self.assertLess(add.index('sw_zend_fci_params_persist('), add.index('scheduler_try_push_slot('))
        free = active[FREE]
        self.assertLess(free.index('scheduler_next_slot('), free.index('sw_zend_fci_cache_discard('))
        self.assertLess(free.index('sw_zend_fci_cache_discard('), free.index('sw_zend_fci_params_discard('))
        self.assertLess(free.index('sw_zend_fci_params_discard('), free.index('efree(task);'))
        self.assertLess(free.index('efree(task);'), free.index('scheduler_drop_slot('))
        self.assertLess(free.index('scheduler_drop_slot('), free.index('zend_object_std_dtor('))
        start = active[START]
        self.assertLess(start.index('SWR_CORO_SCHED_PHASE_START'), start.index('scheduler_next_slot('))
        self.assertLess(start.index('SWR_CORO_SCHED_SLOT_ABSENT'), start.index('while (next_kind'))
        self.assertLess(start.index('swr_v1_phpcoroutines_repeat('), start.index('PHPCoroutine::create('))
        self.assertLess(start.index('efree(task);'), start.rindex('scheduler_next_slot('))
        self.assertLess(start.index('php_swoole_event_wait();'), start.index('scheduler_drop_slot('))
        self.assertLess(start.index('scheduler_drop_slot('), start.index('SWR_CORO_SCHED_PHASE_STOP'))
        self.assertNotIn('for (uint64_t', start)


if __name__ == '__main__':
    unittest.main()
