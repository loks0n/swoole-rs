"""Source-only terminal decisions; no diagnostic/callback/exception/lifetime execution."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from terminal_bodies import SIGNATURES


class TerminalBoundary(unittest.TestCase):
    def test_exact_fallback_and_native_effect_identities(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists(): self.skipTest('Supply pinned source')
        source = pin.read_text(); selected = coroutine_selected(source)
        effects = [
            ['OBJ_RELEASE(EG(exception));', 'EG(exception) = nullptr;', 'zend_exception_error(EG(exception), E_ERROR);'],
            ['Coroutine::count()', 'php_swoole_is_fatal_error()', 'sw_reactor()', 'sw_reactor()->bailout',
             'SWOOLE_G(enable_library)', 'zend::function::call(R"(\\Swoole\\Coroutine\\deadlock_check)", 0, nullptr);'],
            ['auto *ctx = static_cast<PHPContext *>(arg);', '(*ctx->on_close)(ctx);', 'efree(ctx);'],
        ]
        active = []
        for signature, statements in zip(SIGNATURES, effects):
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'; self.assertTrue(after.endswith(suffix))
            current = after[:-len(suffix)]; active.append(current)
            self.assertIn('swr_v1_phpcoroutines_control(', current)
            for statement in statements: self.assertEqual(before.count(statement), current.count(statement), statement)
        self.assertEqual(active[0].count('#if SW_RECOVER_CANCELED_EXCEPTION'), 2)
        self.assertLess(active[0].index('OBJ_RELEASE(EG(exception));'), active[0].index('EG(exception) = nullptr;'))
        original_diagnostic = body(body(source, SIGNATURES[1]), 'else {')
        self.assertIn(original_diagnostic, active[1])
        self.assertLess(active[1].index('SWR_CORO_CONTROL_FATAL_PRESENCE:'), active[1].index('SWR_CORO_CONTROL_REACTOR_PRESENCE:'))
        self.assertLess(active[1].index('SWR_CORO_CONTROL_REACTOR_PRESENCE:'), active[1].index('SWR_CORO_CONTROL_REACTOR_BAILOUT:'))
        self.assertLess(active[2].index('(*ctx->on_close)(ctx);'), active[2].index('efree(ctx);'))
        self.assertNotIn('swr_v1_phpcoroutines_control(ctx', active[2])


if __name__ == '__main__': unittest.main()
