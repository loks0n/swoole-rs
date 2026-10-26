"""Preserve constant config initialization, native effects and public Config ABI."""
import os
from pathlib import Path
import unittest
from overlay import body, coroutine_selected, header_selected


class ConfigBoundary(unittest.TestCase):
    def test_constant_seed_and_native_effects(self):
        root = Path(__file__).resolve().parents[3]
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', root / 'target/upstream/src'))
        if not (pin / 'ext-src/swoole_coroutine.cc').exists():
            self.skipTest('Supply SWOOLE_UPSTREAM_SOURCE for pinned source')
        original = (pin / 'ext-src/swoole_coroutine.cc').read_text()
        selected = coroutine_selected(original)
        for signature in ['void PHPCoroutine::deactivate(void *ptr) {', 'void PHPCoroutine::set_hook_flags(uint32_t flags) {']:
            old, new = body(original, signature), body(selected, signature)
            self.assertEqual(new.split('#else', 1)[1].rsplit('#endif', 1)[0], old)
        signature = 'void PHPCoroutine::set_hook_flags(uint32_t flags) {'
        old_prefix = body(original, signature).split('    config.hook_flags = flags;')[0]
        new_prefix = body(selected, signature).split('#else', 1)[0].split('    swr_v1_phpcoroutines_config(')[0]
        self.assertEqual(new_prefix, '\n#ifdef SWOOLE_RS_PHPCOROUTINES' + old_prefix)
        selected_seed = selected.split('SW_THREAD_LOCAL swr_phpcoroutines_config_state PHPCoroutine::config{', 1)[1].split('};', 1)[0]
        self.assertEqual(selected_seed, '\n    SW_DEFAULT_MAX_CORO_NUM, 0, 0, 0,\n')
        header = (pin / 'ext-src/php_swoole_coroutine.h').read_text()
        self.assertEqual(body(header_selected(header), 'struct Config {'), body(header, 'struct Config {'))


if __name__ == '__main__':
    unittest.main()
