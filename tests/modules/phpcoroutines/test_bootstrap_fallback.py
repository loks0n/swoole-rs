"""Exact pinned fallback for all three frontend bootstrap bodies."""
import os
from pathlib import Path
import unittest
from make_patches import body, selected, coroutine_selected, system_selected


class BootstrapFallback(unittest.TestCase):
    def test_three_native_fallbacks_remain_exact(self):
        source=Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE',Path(__file__).resolve().parents[3]/'target/upstream/src'))
        if not source.exists(): self.skipTest('Supply pinned SWOOLE_UPSTREAM_SOURCE')
        for path,fn,name in [('ext-src/swoole_coroutine.cc',coroutine_selected,'php_swoole_coroutine_minit'),
            ('ext-src/swoole_coroutine_scheduler.cc',selected,'php_swoole_coroutine_scheduler_minit'),
            ('ext-src/swoole_coroutine_system.cc',system_selected,'php_swoole_coroutine_system_minit')]:
            original=(source/path).read_text();signature='void '+name+'(int module_number) {'
            replacement=body(fn(original),signature)
            self.assertTrue(replacement.startswith('\n#ifdef SWOOLE_RS_PHPCOROUTINES\n'))
            self.assertTrue(replacement.endswith('#else\n'+body(original,signature)+'#endif\n'))


if __name__=='__main__': unittest.main()
