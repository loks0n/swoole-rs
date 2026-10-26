"""Source-only lifecycle frontend order; no creation/shutdown/bailout execution."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected
from lifecycle_bodies import SIGNATURES


class LifecycleBoundary(unittest.TestCase):
    def test_exact_fallback_and_fresh_native_effects(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists(): self.skipTest('Supply pinned source')
        source = pin.read_text(); selected = coroutine_selected(source); active = []
        for signature in SIGNATURES:
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'; self.assertTrue(after.endswith(suffix))
            current = after[:-len(suffix)]; active.append(current)
            self.assertIn('swr_v1_phpcoroutines_control(', current)
        create = body(source, SIGNATURES[0])
        self.assertIn(create[:create.index('    if (sw_unlikely(SWOOLE_G(req_status)')], active[0])
        for statement in ['EG(current_execute_data)->prev_execute_data->func;',
                          'php_swoole_fatal_error(E_ERROR, "can not use coroutine in __destruct after php_request_shutdown");',
                          'PHPCoroutine::create(&fci_cache, fci.param_count, fci.params, &fci.function_name);']:
            self.assertEqual(create.count(statement), active[0].count(statement))
        self.assertIn('swr_v1_phpcoroutines_create_destructor(reinterpret_cast<const uint8_t *>(ZSTR_VAL(func->common.function_name)))', active[0])
        self.assertNotIn('ZSTR_LEN', active[0])
        self.assertNotIn('memcmp(', active[0])
        self.assertLess(active[0].index('SWR_CORO_CONTROL_REQUEST_SHUTDOWN:'), active[0].index('SWR_CORO_CONTROL_CALLER_FUNCTION:'))
        self.assertLess(active[0].index('SWR_CORO_CONTROL_CALLER_NAME:'), active[0].index('SWR_CORO_CONTROL_CALLER_DESTRUCTOR:'))
        effects = ['zend_hash_destroy(SWOOLE_G(in_autoload));', 'FREE_HASHTABLE(SWOOLE_G(in_autoload));',
                   'SWOOLE_G(in_autoload) = nullptr;', 'PHPCoroutine::shutdown();']
        positions = [active[1].index(effect) for effect in effects]; self.assertEqual(positions, sorted(positions))
        for effect in effects: self.assertEqual(active[1].count(effect), body(source, SIGNATURES[1]).count(effect))
        self.assertIn('Coroutine::bailout([]() {', active[2])
        for effect in ['sw_reactor()', 'sw_reactor()->running = false;', 'sw_reactor()->bailout = true;', 'zend_bailout();']:
            self.assertEqual(active[2].count(effect), body(source, SIGNATURES[2]).count(effect))
        self.assertLess(active[2].index('sw_reactor()->running = false;'), active[2].index('sw_reactor()->bailout = true;'))
        self.assertLess(active[2].index('sw_reactor()->bailout = true;'), active[2].index('zend_bailout();'))
        self.assertNotIn('swr_v1_phpcoroutines_control(ctx', ''.join(active))


if __name__ == '__main__': unittest.main()
