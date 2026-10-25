"""Source-only full lifecycle boundary; never executes callback/teardown/bailout."""
import os
from pathlib import Path
import unittest
from make_patches import body, coroutine_selected
from context_lifecycle_bodies import CTOR, MAIN, DESTROY, REGISTER


class ContextLifecycleBoundary(unittest.TestCase):
    def test_native_fallback_try_scope_identities_and_publication_order(self):
        pin = Path(os.environ.get('SWOOLE_UPSTREAM_SOURCE', Path(__file__).resolve().parents[3] / 'target/upstream/src')) / 'ext-src/swoole_coroutine.cc'
        if not pin.exists(): self.skipTest('Supply pinned source')
        source = pin.read_text(); selected = coroutine_selected(source); active = {}
        for signature in [CTOR, MAIN, DESTROY, REGISTER]:
            before, after = body(source, signature), body(selected, signature)
            suffix = '#else' + before + '#endif\n'; self.assertTrue(after.endswith(suffix))
            active[signature] = after[:-len(suffix)]
            self.assertIn('swr_v1_phpcoroutines_lifecycle(', active[signature])
        ctor = active[CTOR]
        self.assertLess(ctor.index('ctx->co->set_task((void *) ctx);'), ctor.index('SWR_CORO_LIFECYCLE_CTOR_FIBER:'))
        self.assertIn('ctx->fci.function_name = *args->callable;', ctor)
        self.assertIn('Z_TRY_ADDREF(ctx->fci.function_name);', ctor)
        self.assertIn('ZVAL_UNDEF(&ctx->fci.function_name);', ctor)
        self.assertIn('sw_zend_fci_cache_persist(&ctx->fci_cache);', ctor)
        original_main = body(source, MAIN); main = active[MAIN]
        prefix = original_main[:original_main.index('    zend_first_try {')]
        self.assertIn(prefix, main)
        catch = original_main[original_main.index('    zend_catch {'):original_main.index('    destroy_context(ctx);')]
        self.assertIn(catch, main)
        self.assertLess(main.index('zend_first_try {'), main.index('uint32_t stage = 0;'))
        self.assertLess(main.index('zend_end_try();'), main.rindex('uint32_t stage = 0;'))
        for effect in ['zend_call_function(&ctx->fci, &ctx->fci_cache);', 'exception_caught = catch_exception();',
                       'defer_fci->fci.param_count = 1;', 'defer_fci->fci.params = &ctx->return_value;',
                       'sw_zend_call_function_anyway(&defer_fci->fci, &defer_fci->fci_cache) != SUCCESS',
                       'php_swoole_fatal_error(E_WARNING, "defer callback handler error");',
                       'zend_bailout();', 'sw_zend_fci_cache_discard(&defer_fci->fci_cache);', 'efree(defer_fci);']:
            self.assertEqual(main.count(effect), original_main.count(effect), effect)
        self.assertIn('auto *tasks = ctx->defer_tasks;', main)
        self.assertIn('while (tasks->pop(&defer_fci))', main)
        self.assertLess(main.index('SWR_CORO_LIFECYCLE_DEFER_WARN:'), main.index('SWR_CORO_LIFECYCLE_DEFER_EXCEPTION:'))
        self.assertLess(main.index('SWR_CORO_LIFECYCLE_POST_DESTROY:'), main.index('SWR_CORO_LIFECYCLE_POST_EXCEPTION:'))
        destroy = active[DESTROY]; original_destroy = body(source, DESTROY)
        prefix = original_destroy[:original_destroy.index('    if (swoole_isset_hook(')]
        self.assertIn(prefix, destroy)
        self.assertIn('while (ctx->defer_tasks->pop(&defer_fci))', destroy)
        for effect in ['SG(request_info).no_headers = true;', 'php_output_end_all();', 'php_output_deactivate();',
                       'php_output_activate();', 'SG(request_info).no_headers = no_headers;',
                       'ctx->context = reinterpret_cast<zend_object *>(INVALID_PTR);', 'OBJ_RELEASE(context);',
                       'Z_TRY_DELREF(ctx->fci.function_name);', 'ZVAL_UNDEF(&ctx->fci.function_name);',
                       'sw_zend_fci_cache_discard(&ctx->fci_cache);', 'Z_TRY_DELREF(ctx->return_value);',
                       'fiber_context_try_destroy(ctx, origin_ctx);', 'zend_vm_stack_destroy();', 'restore_context(origin_ctx);']:
            self.assertEqual(destroy.count(effect), original_destroy.count(effect), effect)
        self.assertLess(destroy.index('ctx->context = reinterpret_cast<zend_object *>(INVALID_PTR);'), destroy.index('OBJ_RELEASE(context);'))
        register = active[REGISTER]
        self.assertIn('ctx = get_context();', register)
        self.assertIn('ctx->defer_tasks = new PHPCoroutineDeferredTasks;', register)
        self.assertIn('ctx->defer_tasks->push(fci);', register)
        self.assertNotIn('swr_v1_phpcoroutines_lifecycle(ctx', ''.join(active.values()))


if __name__ == '__main__': unittest.main()
