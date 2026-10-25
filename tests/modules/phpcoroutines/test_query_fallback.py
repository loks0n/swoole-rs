"""Exact original fallback bodies for the query/introspection frontend changes."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected


class QueryFallback(unittest.TestCase):
    def test_original_native_query_and_trace_bodies_are_unchanged(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists():
            self.skipTest('Supply SWOOLE_UPSTREAM_SOURCE for pinned source')
        source = pin.read_text()
        selected = coroutine_selected(source)
        signatures = ['static PHP_METHOD(swoole_coroutine, getContext) {',
            'PHP_METHOD(swoole_coroutine, getPcid) {', 'static PHP_METHOD(swoole_coroutine, getStackUsage) {',
            'static PHP_METHOD(swoole_coroutine, getBackTrace) {',
            'void sw_php_print_backtrace(zend_long cid, zend_long options, zend_long limit, zval *return_value) {']
        for signature in signatures:
            original, replacement = body(source, signature), body(selected, signature)
            self.assertEqual(replacement.split('#else', 1)[1].rsplit('#endif', 1)[0], '\n' + original)


if __name__ == '__main__':
    unittest.main()
