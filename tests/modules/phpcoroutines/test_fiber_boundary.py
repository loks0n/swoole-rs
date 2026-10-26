"""Source-only observer policy/caller custody; no fiber/observer execution."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from fiber_bodies import SIGNATURES


class FiberBoundary(unittest.TestCase):
    def test_native_fallback_and_effect_custody(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        overlay = coroutine_selected(original)
        for signature in SIGNATURES:
            before, after = body(original, signature), body(overlay, signature)
            selected, fallback = after.split('#else', 1)
            self.assertEqual(fallback.rsplit('#endif', 1)[0], before)
            self.assertIn('swr_v1_phpcoroutines_metadata(' if 'switch_notify(' in signature and 'try_notify(' not in signature else 'swr_v1_phpcoroutines_fiber(', selected)
        status = body(overlay, SIGNATURES[0]).split('#else\n', 1)[0]
        self.assertEqual(status.count('ctx->co->get_state()'), 1)
        self.assertIn('ctx->fiber_context == EG(main_fiber_context)', status)
        for state, outcome in [('INIT', 'INIT'), ('WAITING', 'SUSPENDED'), ('RUNNING', 'RUNNING'), ('END', 'DEAD')]:
            self.assertIn('case Coroutine::STATE_' + state + ':\n        return ZEND_FIBER_STATUS_' + outcome + ';', body(original, SIGNATURES[0]))
        switch = body(overlay, SIGNATURES[1]).split('#else\n', 1)[0]
        # Capture original native identities once; refresh only the same status
        # query after the observer returns, then publish the flag. Rust receives
        # copied facts and no Zend/context pointer.
        for statement in ['zend_fiber_context *from_context = from->fiber_context;',
                          'zend_fiber_context *to_context = to->fiber_context;',
                          'from_context->status = fiber_get_status(from);',
                          'to_context->status = fiber_get_status(to);',
                          'to_context->status = ZEND_FIBER_STATUS_INIT;',
                          'zend_observer_fiber_switch_notify(from_context, to_context);']:
            self.assertIn(statement, switch)
        self.assertIn('SWR_CORO_METADATA_FIBER, &cells', switch)
        self.assertNotIn('to->fiber_init_notified =', switch)
        self.assertEqual(switch.count('to_context->status = fiber_get_status(to);'), 2)
        for name in ['fiber_context_init(PHPContext *ctx)']:
            signature = 'void PHPCoroutine::' + name + ' {'
            self.assertEqual(body(original, signature), body(overlay, signature))

    def test_destroy_refreshes_presence_after_native_observers(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not path.exists(): self.skipTest('Supply pinned source')
        source = path.read_text(); selected = coroutine_selected(source)
        active = body(selected, SIGNATURES[3]).split('#else', 1)[0]
        for statement in ['ctx->fiber_context->status = ZEND_FIBER_STATUS_DEAD;',
                          'fiber_context_switch_try_notify(ctx, origin_ctx);',
                          'zend_observer_fiber_destroy_notify(ctx->fiber_context);',
                          'efree(ctx->fiber_context);']:
            self.assertEqual(active.count(statement), body(source, SIGNATURES[3]).count(statement))
        self.assertEqual(active.count('observation = ctx->fiber_context != nullptr;'), 2)
        self.assertLess(active.index('SWR_CORO_FIBER_DESTROY_NOTIFY:'), active.index('SWR_CORO_FIBER_REFRESH_PRESENT:'))
        self.assertLess(active.index('SWR_CORO_FIBER_REFRESH_PRESENT:'), active.index('SWR_CORO_FIBER_FREE:'))


if __name__ == '__main__':
    unittest.main()
