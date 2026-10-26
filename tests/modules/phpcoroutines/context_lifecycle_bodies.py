"""Whole context policy, Native try/catch/storage/effects and existing queue custody."""
import textwrap
CTOR = 'PHPContext *PHPCoroutine::create_context(const Args *args) {'
MAIN = 'void PHPCoroutine::main_func(void *_args) {'
DESTROY = 'void PHPCoroutine::destroy_context(PHPContext *ctx) {'
REGISTER = 'void PHPCoroutine::defer(zend::Function *fci) {'


def block(text, indent):
    return textwrap.indent(textwrap.dedent(text).strip('\n'), indent)


def cases(entries, indent='    '):
    result = ''
    for name, effect in entries:
        result += indent + '    case SWR_CORO_LIFECYCLE_' + name + ': {\n'
        result += block(effect, indent + '        ') + '\n'
        if name not in ('DONE', 'CTOR_RETURN'):
            result += indent + '        break;\n'
        result += indent + '    }\n'
    return result


def drive(kind, entries, indent='    '):
    return indent + 'uint32_t stage = 0;\n' + indent + 'int64_t observation = 0;\n' + indent + 'for (;;) {\n' + indent + '    switch (swr_v1_phpcoroutines_lifecycle(&stage, SWR_CORO_LIFECYCLE_' + kind + ', observation)) {\n' + cases(entries, indent) + indent + '    }\n' + indent + '}\n'


def replace_context_lifecycle(source, result, body):
    original = body(source, CTOR)
    current = body(result, CTOR)
    suffix = '#else' + original + '#endif\n'
    if not current.endswith(suffix): raise ValueError('Expected selected metadata constructor')
    active = current[:-len(suffix)]
    guard = '\n#ifdef SWOOLE_RS_PHPCOROUTINES'
    if not active.startswith(guard): raise ValueError('Unexpected constructor guard')
    active = active[len(guard):]
    fiber = '''    if (UNEXPECTED(SWOOLE_G(enable_fiber_mock))) {
        fiber_context_init(ctx);
    } else {
        ctx->fiber_context = nullptr;
    }'''
    callable_group = '''    if (args->callable) {
        ctx->fci.function_name = *args->callable;
        Z_TRY_ADDREF(ctx->fci.function_name);
    } else {
        ZVAL_UNDEF(&ctx->fci.function_name);
    }'''
    if active.count(fiber) != 1 or active.count(callable_group) != 1:
        raise ValueError('Pinned constructor branch changed')
    initialize, rest = active.split(fiber)
    vm, tail = rest.split(callable_group)
    if tail.strip() != 'sw_zend_fci_cache_persist(&ctx->fci_cache);\n\n    return ctx;':
        raise ValueError('Constructor persistence/return order changed')
    initialize = initialize.replace('auto *ctx = static_cast<PHPContext *>(emalloc(sizeof(PHPContext)));',
                                    'ctx = static_cast<PHPContext *>(emalloc(sizeof(PHPContext)));')
    selected = '\n    PHPContext *ctx = nullptr;\n' + drive('CTOR', [
        ('CTOR_INIT', initialize), ('CTOR_FIBER', 'observation = SWOOLE_G(enable_fiber_mock) != 0;'),
        ('CTOR_FIBER_INIT', 'fiber_context_init(ctx);'), ('CTOR_FIBER_NONE', 'ctx->fiber_context = nullptr;'),
        ('CTOR_VM', vm), ('CTOR_CALLABLE', 'observation = args->callable != nullptr;'),
        ('CTOR_CALLABLE_COPY', 'ctx->fci.function_name = *args->callable;\nZ_TRY_ADDREF(ctx->fci.function_name);'),
        ('CTOR_CALLABLE_UNDEF', 'ZVAL_UNDEF(&ctx->fci.function_name);'),
        ('CTOR_PERSIST', 'sw_zend_fci_cache_persist(&ctx->fci_cache);'), ('CTOR_RETURN', 'return ctx;')])
    result = result.replace(CTOR + current + '}', CTOR + guard + selected + '#else' + original + '#endif\n}')

    original = body(source, DESTROY)
    prefix = original[:original.index('    if (swoole_isset_hook(')]
    context_release = body(original, 'if (ctx->context) {')
    # v6.2.4 keeps the origin lookup out of the yielding release; keep its rationale with the release.
    rationale = '''/*
 * Object destruction may yield and allow the origin coroutine to exit.
 * Do not cache its context across resource cleanup; resolve it immediately before each use.
 */'''
    if rationale.replace('\n', '\n    ') not in original:
        raise ValueError('Pinned destroy-context rationale changed')
    context_release = rationale + '\n' + context_release
    resources = original[original.index('    Z_TRY_DELREF(ctx->fci.function_name);'):]
    selected = prefix + '    zend_bool no_headers = false;\n' + drive('DESTROY', [
        ('DONE', 'return;'),
        ('DESTROY_HOOK', 'observation = swoole_isset_hook(SW_GLOBAL_HOOK_ON_CORO_STOP);'),
        ('DESTROY_HOOK_CALL', 'swoole_call_hook(SW_GLOBAL_HOOK_ON_CORO_STOP, ctx);'),
        ('DESTROY_OUTPUT', 'observation = OG(handlers).elements != 0;'),
        ('DESTROY_SAVE_HEADERS', 'no_headers = SG(request_info).no_headers;\n/* Do not send headers by SAPI */\nSG(request_info).no_headers = true;'),
        ('DESTROY_ACTIVE', 'observation = OG(active) != 0;'),
        ('DESTROY_END_OUTPUT', 'php_output_end_all();'),
        ('DESTROY_RESTART_OUTPUT', 'php_output_deactivate();\nphp_output_activate();\nSG(request_info).no_headers = no_headers;'),
        ('DESTROY_DEFER', 'observation = ctx->defer_tasks != nullptr;'),
        ('DESTROY_DEFER_DRAIN', '''zend::Function *defer_fci = nullptr;
while (ctx->defer_tasks->pop(&defer_fci)) {
    sw_zend_fci_cache_discard(&defer_fci->fci_cache);
    efree(defer_fci);
}
delete ctx->defer_tasks;
ctx->defer_tasks = nullptr;'''),
        ('DESTROY_OBJECT', 'observation = ctx->context != nullptr;'),
        ('DESTROY_OBJECT_RELEASE', context_release), ('DESTROY_RESOURCES', resources)])
    result = result.replace(DESTROY + original + '}', DESTROY + guard + selected + '#else' + original + '#endif\n}')

    original = body(source, MAIN)
    prefix = original[:original.index('    zend_first_try {')]
    trace = original.split('    zend_first_try {', 1)[1].split('        if (swoole_isset_hook(', 1)[0]
    fiber_notify = body(original, 'if (UNEXPECTED(ctx->fiber_context && ctx->fci_cache.function_handler->type == ZEND_USER_FUNCTION)) {')
    invoke = original[original.index('        zend_call_function(&ctx->fci, &ctx->fci_cache);'):original.index('        // The defer tasks still need')]
    catch = original[original.index('    zend_catch {'):original.index('    destroy_context(ctx);')]
    deferred_effects = [
        ('DEFER_VALUE', 'observation = Z_TYPE_P(&ctx->return_value) != IS_UNDEF;'),
        ('DEFER_PARAMS', 'defer_fci->fci.param_count = 1;\ndefer_fci->fci.params = &ctx->return_value;'),
        ('DEFER_INVOKE', 'observation = sw_zend_call_function_anyway(&defer_fci->fci, &defer_fci->fci_cache) != SUCCESS;'),
        ('DEFER_WARN', 'php_swoole_fatal_error(E_WARNING, "defer callback handler error");'),
        ('DEFER_EXCEPTION', 'observation = EG(exception) != nullptr;'),
        ('DEFER_BAILOUT', 'zend_bailout();'),
        ('DEFER_CLEAN', 'sw_zend_fci_cache_discard(&defer_fci->fci_cache);\nefree(defer_fci);')]
    drain = '''auto *tasks = ctx->defer_tasks;
zend::Function *defer_fci = nullptr;
while (tasks->pop(&defer_fci)) {
    uint32_t stage = 0;
    int64_t observation = 0;
    for (uint32_t action = swr_v1_phpcoroutines_lifecycle(&stage, SWR_CORO_LIFECYCLE_DEFER, observation);
         action != SWR_CORO_LIFECYCLE_DONE;
         action = swr_v1_phpcoroutines_lifecycle(&stage, SWR_CORO_LIFECYCLE_DEFER, observation)) {
        switch (action) {
''' + cases(deferred_effects, '        ') + '''        }
    }
}
delete ctx->defer_tasks;
ctx->defer_tasks = nullptr;'''
    entries = [
        ('MAIN_TRACE', trace), ('MAIN_HOOK', 'observation = swoole_isset_hook(SW_GLOBAL_HOOK_ON_CORO_START);'),
        ('MAIN_HOOK_CALL', 'swoole_call_hook(SW_GLOBAL_HOOK_ON_CORO_START, ctx);'),
        ('MAIN_FIBER', 'observation = ctx->fiber_context != nullptr;'),
        ('MAIN_USER_FUNCTION', 'observation = ctx->fci_cache.function_handler->type == ZEND_USER_FUNCTION;'),
        ('MAIN_NOTIFY', fiber_notify), ('MAIN_INVOKE', invoke),
        ('MAIN_DEFER', 'observation = ctx->defer_tasks != nullptr;'), ('MAIN_DEFER_DRAIN', drain)]
    # This stage is INSIDE the Native try block and discarded on longjmp. No
    # mutated cursor is ever read in catch or after zend_end_try.
    selected = prefix + '''    zend_first_try {
        uint32_t stage = 0;
        int64_t observation = 0;
        for (uint32_t action = swr_v1_phpcoroutines_lifecycle(&stage, SWR_CORO_LIFECYCLE_MAIN, observation);
             action != SWR_CORO_LIFECYCLE_DONE;
             action = swr_v1_phpcoroutines_lifecycle(&stage, SWR_CORO_LIFECYCLE_MAIN, observation)) {
            switch (action) {
''' + cases(entries, '            ') + '''            }
        }
    }
''' + catch + drive('POST', [('DONE', 'return;'), ('POST_DESTROY', 'destroy_context(ctx);'),
                             ('POST_EXCEPTION', 'observation = exception_caught;'), ('POST_BAILOUT', 'bailout();')])
    result = result.replace(MAIN + original + '}', MAIN + guard + selected + '#else' + original + '#endif\n}')

    original = body(source, REGISTER)
    selected = '\n    PHPContext *ctx = nullptr;\n' + drive('REGISTER', [
        ('DONE', 'return;'), ('REGISTER_CONTEXT', 'ctx = get_context();'),
        ('REGISTER_OWNER', 'observation = ctx->defer_tasks != nullptr;'),
        ('REGISTER_ALLOCATE', 'ctx->defer_tasks = new PHPCoroutineDeferredTasks;'),
        ('REGISTER_PUSH', 'ctx->defer_tasks->push(fci);')])
    return result.replace(REGISTER + original + '}', REGISTER + guard + selected + '#else' + original + '#endif\n}')
