"""Source-only context notification custody; no callbacks/context execution."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from transfer_bodies import NOTIFICATION_SIGNATURES


class NotificationBoundary(unittest.TestCase):
    def test_exact_native_prefix_effects_and_fallback(self):
        root = Path(__file__).resolve().parents[3]
        path = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not path.exists():
            self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        original = path.read_text()
        overlay = coroutine_selected(original)
        for signature in NOTIFICATION_SIGNATURES:
            before, after = body(original, signature), body(overlay, signature)
            active, fallback = after.split('#else', 1)
            self.assertEqual(fallback.rsplit('#endif', 1)[0], before)
            self.assertIn(before[:before.index('    fiber_context_switch_try_notify(')], active)
            self.assertIn('swr_v1_phpcoroutines_transfer(&stage,', active)
            for line in before.splitlines():
                statement = line.strip()
                if statement.startswith(('fiber_context_switch_try_notify(', 'save_context(', 'restore_context(',
                                         'record_last_msec(', '(*ctx->', 'swoole_trace_log(')):
                    self.assertEqual(active.count(statement), 1)
            self.assertIn('observation = ctx->on_', active)
        close = 'void PHPCoroutine::on_close(void *arg) {'
        before, after = body(original, close), body(overlay, close)
        suffix = '#else' + before + '#endif\n'
        self.assertTrue(after.endswith(suffix))
        active = after[:-len(suffix)]
        self.assertEqual(active.count('(*ctx->on_close)(ctx);'), 1)
        self.assertEqual(active.count('efree(ctx);'), 1)
        self.assertLess(active.index('(*ctx->on_close)(ctx);'), active.index('efree(ctx);'))


if __name__ == '__main__':
    unittest.main()
