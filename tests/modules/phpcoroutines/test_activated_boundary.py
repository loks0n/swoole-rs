"""Exact activated Native fallback/seed and publication effects, source only."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected, header_selected
from activated_bodies import ACTIVATED_SIGNATURE, ACTIVATED_SELECTED_DECL


class ActivatedBoundary(unittest.TestCase):
    def test_constant_seed_and_preserved_effect_publication_points(self):
        root = Path(__file__).resolve().parents[3]
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src'))
        if not pin.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        source = (pin / 'ext-src/swoole_coroutine.cc').read_text()
        selected = coroutine_selected(source)
        header = header_selected((pin / 'ext-src/php_swoole_coroutine.h').read_text())
        self.assertIn(ACTIVATED_SELECTED_DECL, header)
        self.assertIn('SW_THREAD_LOCAL swr_phpcoroutines_activation_state PHPCoroutine::activated{0};', selected)
        self.assertIn('SW_THREAD_LOCAL bool PHPCoroutine::activated = false;', selected)
        for signature in ['void PHPCoroutine::activate() {', 'void PHPCoroutine::deactivate(void *ptr) {',
                          'void PHPCoroutine::shutdown() {']:
            before, after = body(source, signature), body(selected, signature)
            active, fallback = after.split('#else', 1)
            self.assertEqual(fallback.rsplit('#endif', 1)[0], ('\n' + before) if signature == 'void PHPCoroutine::activate() {' else before)
            self.assertNotIn('activated =', active)
        activate = body(selected, 'void PHPCoroutine::activate() {').split('#else', 1)[0]
        self.assertLess(activate.index('Coroutine::set_on_close(on_close);'), activate.index('SWR_CORO_SCHED_PHASE_START'))
        deactivate = body(selected, 'void PHPCoroutine::deactivate(void *ptr) {').split('#else', 1)[0]
        self.assertLess(deactivate.index('if (sw_unlikely(!is_activated()))'), deactivate.index('SWR_CORO_SCHED_PHASE_STOP'))
        self.assertLess(deactivate.index('SWR_CORO_SCHED_PHASE_STOP'), deactivate.index('interrupt_thread_stop();'))
        for signature in ['void PHPCoroutine::interrupt_thread_start() {', 'void PHPCoroutine::interrupt_thread_stop() {']:
            before, after = body(source, signature), body(selected, signature)
            self.assertTrue(after.endswith('#else' + before + '#endif\n'))
        for helper in ['static inline long get_cid() {', 'static inline long get_elapsed(long cid = 0) {',
                       'static inline long get_execute_time(long cid = 0) {']:
            active = body(header, helper).split('#else', 1)[0]
            self.assertIn('is_activated()', active)
            self.assertNotIn('swr_v1_phpcoroutines_context_route(', active)
        self.assertIn('swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_READ)', body(header, ACTIVATED_SIGNATURE))


if __name__ == '__main__':
    unittest.main()
