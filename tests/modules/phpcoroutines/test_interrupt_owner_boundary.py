"""Exact source-only whole flag-reader closure; no actual interrupt thread/probe."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected, header_selected
from interrupt_bodies import SIGNATURES, DECL, SELECTED_DECL


class InterruptOwnerBoundary(unittest.TestCase):
    def test_all_original_flag_readers_publications_and_scope(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src'))
        if not (pin / 'ext-src/swoole_coroutine.cc').exists(): self.skipTest('Supply pinned source')
        source = (pin / 'ext-src/swoole_coroutine.cc').read_text()
        header = (pin / 'ext-src/php_swoole_coroutine.h').read_text()
        selected = coroutine_selected(source); selected_header = header_selected(header)
        seed = 'SW_THREAD_LOCAL std::atomic_bool PHPCoroutine::interrupt_thread_running{false};'
        self.assertEqual(source.count(seed), 1)
        self.assertIn('SW_THREAD_LOCAL swr_phpcoroutines_interrupt_state PHPCoroutine::interrupt_thread_running{0};', selected)
        self.assertIn(SELECTED_DECL, selected_header)
        source_remainder = source.replace(seed, '')
        active = []
        for signature in SIGNATURES:
            before, after = body(source, signature), body(selected, signature)
            self.assertTrue(after.endswith('#else' + before + '#endif\n'))
            current = after[:-len('#else' + before + '#endif\n')]; active.append(current)
            source_remainder = source_remainder.replace(signature + before + '}', '')
            self.assertNotIn('if (interrupt_thread_running)', current)
            self.assertNotIn('!interrupt_thread_running', current)
            self.assertNotIn('interrupt_thread_running =', current)
        self.assertNotIn('interrupt_thread_running', source_remainder)
        record = 'static void record_last_msec(PHPContext *ctx) {'
        before, after = body(header, record), body(selected_header, record)
        self.assertTrue(after.endswith('#else' + before + '#endif\n    '))
        current = after.split('#else', 1)[0]
        self.assertIn('swr_v1_phpcoroutines_interrupt(&interrupt_thread_running, &interrupt_stage, SWR_CORO_INTERRUPT_RECORD', current)
        self.assertLess(current.index('swr_v1_phpcoroutines_interrupt('), current.index('Timer::get_absolute_msec();'))
        self.assertLess(current.index('Timer::get_absolute_msec();'), current.index('SWR_CORO_METADATA_RECORD'))
        schedulable = 'static inline bool is_schedulable(PHPContext *ctx) {'
        native_schedulable, selected_schedulable = body(header, schedulable), body(selected_header, schedulable)
        self.assertTrue(selected_schedulable.endswith('#else' + native_schedulable + '#endif\n    '))
        current = selected_schedulable.split('#else', 1)[0]
        self.assertLess(current.index('SWR_CORO_INTERRUPT_RECORD'), current.index('Timer::get_absolute_msec();'))
        header_remainder = header.replace(DECL, '').replace(record + before + '}', '').replace(schedulable + native_schedulable + '}', '')
        self.assertNotIn('interrupt_thread_running', header_remainder)
        start, stop = active
        for effect in ['&EG(vm_interrupt);', 'swoole_signal_block_all();', 'zend_atomic_bool_store(vm_interrupt, 1);']:
            self.assertEqual(start.count(effect), body(source, SIGNATURES[0]).count(effect))
        # The helper gets the owner thread's cells, never its own thread-local copies.
        self.assertIn('interrupt_thread = std::thread([running, vm_interrupt]() {', start)
        child = body(start, 'std::thread([running, vm_interrupt]() {')
        self.assertIn('swr_v1_phpcoroutines_interrupt(running, &child_stage, SWR_CORO_INTERRUPT_CHILD', child)
        self.assertNotIn('interrupt_thread_running', child)
        self.assertLess(child.index('swoole_signal_block_all();'), child.index('swr_v1_phpcoroutines_interrupt('))
        self.assertIn('std::this_thread::sleep_for(std::chrono::milliseconds(child.value));', child)
        self.assertEqual(stop.count('interrupt_thread.join();'), 1)
        self.assertIn('SW_THREAD_LOCAL std::thread PHPCoroutine::interrupt_thread;', selected)
        self.assertNotIn('zend_vm_interrupt', selected)

if __name__ == '__main__': unittest.main()
