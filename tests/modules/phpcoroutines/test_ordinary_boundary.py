"""Source-only stack arithmetic and repeat-loop boundary; no stack/sleep effect."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from ordinary_bodies import BOUNDS, KERNEL


class OrdinaryBoundary(unittest.TestCase):
    def test_exact_fallback_and_native_projection_effects(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists(): self.skipTest('Supply pinned source')
        source = pin.read_text(); selected = coroutine_selected(source)
        active = []
        for signature in BOUNDS + [KERNEL]:
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'; self.assertTrue(after.endswith(suffix))
            active.append(after[:-len(suffix)])
        for current in active[:2]:
            self.assertIn('#ifdef SW_USE_THREAD_CONTEXT', current)
            self.assertIn('#ifndef SW_USE_THREAD_CONTEXT', current)
            self.assertIn('#ifdef __APPLE__', current)
            self.assertIn('observation = ctx->co != nullptr;', current)
            self.assertIn('swr_v1_phpcoroutines_bounds(', current)
        self.assertEqual(active[0].count('EG(reserved_stack_size)'), 1)
        self.assertNotIn('EG(reserved_stack_size)', active[1])
        self.assertIn('(int8_t *) ctx->co->get_ctx().get_stack() + plan.reserve', active[0])
        self.assertIn('(void *) ((uintptr_t) ctx->co->get_ctx().get_stack() + ctx->co->get_ctx().get_stack_size())', active[1])
        original_kernel = body(source, KERNEL)
        prefix = original_kernel[:original_kernel.index('    Coroutine::create(')]
        self.assertIn(prefix, active[2])
        self.assertIn('Coroutine::create([=](void *ptr) {', active[2])
        self.assertIn('swr_phpcoroutines_repeat_state repeat{static_cast<int64_t>(count), 0, 0};', active[2])
        self.assertIn('while (swr_v1_phpcoroutines_repeat(&repeat))', active[2])
        self.assertEqual(active[2].count('System::sleep(sleep_time);'), 1)
        self.assertNotIn('SW_LOOP_N(count)', active[2])


if __name__ == '__main__': unittest.main()
