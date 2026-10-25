"""Remaining ordinary stack/repeat arithmetic; Native pointers/effects retained."""
BOUNDS = ['void *PHPCoroutine::stack_limit(PHPContext *ctx) {', 'void *PHPCoroutine::stack_base(PHPContext *ctx) {']
KERNEL = 'PHP_FUNCTION(swoole_test_kernel_coroutine) {'


def replace_ordinary(source, result, body):
    for signature, kind in zip(BOUNDS, ['LIMIT', 'BASE']):
        original = body(source, signature)
        selected = '''
    swr_phpcoroutines_bounds_state state{0, 0};
    uintptr_t observation = 0;
    uint8_t caps = 0;
#ifdef SW_USE_THREAD_CONTEXT
    caps |= 1;
#endif
#ifdef __APPLE__
    caps |= 2;
#endif
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_bounds(&state, SWR_CORO_BOUNDS_''' + kind + ''', caps, observation);
        switch (plan.action) {
        case SWR_CORO_BOUNDS_NULL: return nullptr;
#ifndef SW_USE_THREAD_CONTEXT
        case SWR_CORO_BOUNDS_HAS_CO: observation = ctx->co != nullptr; break;
'''
        if kind == 'LIMIT':
            selected += '        case SWR_CORO_BOUNDS_RESERVE: static_assert(sizeof(zend_ulong) == sizeof(uintptr_t), "Native reserve width"); observation = EG(reserved_stack_size); break;\n'
        selected += ('        case SWR_CORO_BOUNDS_LIMIT_POINTER: return (int8_t *) ctx->co->get_ctx().get_stack() + plan.reserve;\n' if kind == 'LIMIT' else
                     '        case SWR_CORO_BOUNDS_BASE_POINTER: return (void *) ((uintptr_t) ctx->co->get_ctx().get_stack() + ctx->co->get_ctx().get_stack_size());\n')
        selected += '#endif\n        }\n    }\n'
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + selected + '#else' + original + '#endif\n}')
    original = body(source, KERNEL)
    old = '''        SW_LOOP_N(count) {
            System::sleep(sleep_time);
        }'''
    if original.count(old) != 1: raise ValueError('Pinned repeat sleep loop changed')
    selected = original.replace(old, '''        swr_phpcoroutines_repeat_state repeat{static_cast<int64_t>(count), 0, 0};
        while (swr_v1_phpcoroutines_repeat(&repeat)) {
            System::sleep(sleep_time);
        }''')
    return result.replace(KERNEL + original + '}', KERNEL + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' + selected + '#else' + original + '#endif\n}')
