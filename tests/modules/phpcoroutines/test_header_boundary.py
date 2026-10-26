"""Read-only exact-pin proof that selected header edits stay within granted bodies."""
import hashlib
import os
from pathlib import Path
import unittest

from metadata_bodies import FIELDS
from config_bodies import CONFIG_SIGNATURES, CONFIG_DECL, CONFIG_SELECTED_DECL
from activated_bodies import ACTIVATED_DECL, ACTIVATED_SELECTED_DECL
from interrupt_bodies import DECL as INTERRUPT_DECL, SELECTED_DECL as INTERRUPT_SELECTED_DECL
from overlay import HEADER_SHA, HEADER_SIGNATURES, body, header_selected


class HeaderBoundary(unittest.TestCase):
    def test_native_fallback_and_ungranted_header_are_exact(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/php_swoole_coroutine.h'
        if not pin.exists():
            self.skipTest('Pinned header unavailable at host path; complete SDK gate checks both OS captures')
        original = pin.read_text()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), HEADER_SHA)
        selected = header_selected(original)
        for signature in HEADER_SIGNATURES + CONFIG_SIGNATURES + ['static inline void init_main_context() {']:
            old, new = body(original, signature), body(selected, signature)
            self.assertEqual(new.split('#else', 1)[1].rsplit('#endif', 1)[0], old)
            selected = selected.replace(signature + new + '}', signature + old + '}')
        selected = selected.replace('#ifdef SWOOLE_RS_PHPCOROUTINES\n#include "swoole_rs_phpcoroutines.h"\n#endif\n', '')
        selected = selected.replace('#ifdef SWOOLE_RS_PHPCOROUTINES\nstruct PHPCoroutineDeferredTasks;\n#endif\n\n', '')
        selected = selected.replace('#ifdef SWOOLE_RS_PHPCOROUTINES\n    PHPCoroutineDeferredTasks *defer_tasks;\n#else\n    std::stack<zend::Function *> *defer_tasks;\n#endif', '    std::stack<zend::Function *> *defer_tasks;')
        selected = selected.replace(CONFIG_SELECTED_DECL, CONFIG_DECL)
        selected = selected.replace(ACTIVATED_SELECTED_DECL, ACTIVATED_DECL)
        self.assertEqual(selected.count(INTERRUPT_SELECTED_DECL), 1)
        selected = selected.replace(INTERRUPT_SELECTED_DECL, INTERRUPT_DECL)
        for field, selected_type in FIELDS.items():
            native_type = {'ori_error_reporting': 'int', 'tmp_error_reporting': 'int', 'pcid': 'long', 'last_msec': 'int64_t'}.get(field, 'bool')
            old = f'    {native_type} {field};'
            new = '#ifdef SWOOLE_RS_PHPCOROUTINES\n    ' + selected_type + ' ' + field + ';\n#else\n' + old + '\n#endif'
            self.assertEqual(selected.count(new), 1)
            selected = selected.replace(new, old)
        start = selected.index('\n#ifdef SWOOLE_RS_PHPCOROUTINES\nstatic inline swr_phpcoroutines_context_cells')
        end = selected.index('#endif\n\nclass PHPCoroutine {', start) + len('#endif\n\n')
        helper = selected[start:end]
        self.assertEqual(body(helper, 'static inline swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *ctx) {'), '''
    if (!ctx) {
        return {};
    }
    return {&ctx->in_silence, &ctx->enable_scheduler, &ctx->ori_error_reporting,
            &ctx->tmp_error_reporting, &ctx->fiber_init_notified, &ctx->pcid, &ctx->last_msec};
''')
        self.assertEqual(helper.count('static_assert('), 8)
        selected = selected[:start] + selected[end:]
        self.assertEqual(selected, original)


if __name__ == '__main__':
    unittest.main()
