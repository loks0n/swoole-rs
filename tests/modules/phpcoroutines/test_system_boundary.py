"""Preserve every ungranted System byte and all original native fallback bodies."""
import os
from pathlib import Path
import unittest

from make_patches import body, system_selected
from system_control_bodies import SIGNATURES
from method_catalogue_bodies import BRIDGE, declarations, selected_table


class SystemBoundary(unittest.TestCase):
    def test_only_ordinary_and_bootstrap_bodies_and_guarded_include_change(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine_system.cc'
        if not pin.exists():
            self.skipTest('Pinned System TU unavailable; supply SWOOLE_UPSTREAM_SOURCE')
        original = pin.read_text()
        selected = system_selected(original)
        signatures = ['PHP_METHOD(swoole_coroutine_system, ' + method + ') {'
                      for method in ('sleep', 'readFile', 'writeFile', 'getaddrinfo', 'statvfs')]
        signatures += ['PHP_FUNCTION(swoole_coroutine_gethostbyname) {', 'void php_swoole_coroutine_system_minit(int module_number) {']
        signatures += SIGNATURES
        for signature in signatures:
            old, new = body(original, signature), body(selected, signature)
            self.assertEqual(new.split('#else', 1)[1].rsplit('#endif', 1)[0], old if signature in SIGNATURES else '\n' + old)
            selected = selected.replace(signature + new + '}', signature + old + '}')
        selected = selected.replace('\n#ifdef SWOOLE_RS_PHPCOROUTINES\n#include "swoole_rs_phpcoroutines.h"\n#include "phpcoroutines_registration.h"\n#endif', '')
        for table in declarations(original):
            self.assertEqual(selected.count(selected_table(table)), 1)
            selected = selected.replace(selected_table(table), table[0])
        self.assertEqual(selected.count(BRIDGE), 1)
        selected = selected.replace(BRIDGE, '')
        self.assertEqual(selected, original)


if __name__ == '__main__':
    unittest.main()
