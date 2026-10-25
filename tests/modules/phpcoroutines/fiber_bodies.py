"""Fiber observer policy; original native reads/effects and fallback stay native."""
SIGNATURES = ['zend_fiber_status PHPCoroutine::fiber_get_status(const PHPContext *ctx) {',
    'void PHPCoroutine::fiber_context_switch_notify(const PHPContext *from, PHPContext *to) {',
    'void PHPCoroutine::fiber_context_switch_try_notify(const PHPContext *from, PHPContext *to) {',
    'void PHPCoroutine::fiber_context_try_destroy(const PHPContext *ctx, PHPContext *origin_ctx) {']


def replace_fibers(source, result, body):
    replacements = [r'''
    const swr_phpcoroutines_fiber_states states{
        Coroutine::STATE_INIT, Coroutine::STATE_WAITING, Coroutine::STATE_RUNNING, Coroutine::STATE_END};
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_fiber(&stage, SWR_CORO_FIBER_STATUS, observation, &states)) {
        case SWR_CORO_FIBER_MAIN: observation = ctx->fiber_context == EG(main_fiber_context); break;
        case SWR_CORO_FIBER_STATE: observation = ctx->co->get_state(); break;
        case SWR_CORO_FIBER_RUNNING: return ZEND_FIBER_STATUS_RUNNING;
        case SWR_CORO_FIBER_INIT: return ZEND_FIBER_STATUS_INIT;
        case SWR_CORO_FIBER_SUSPENDED: return ZEND_FIBER_STATUS_SUSPENDED;
        case SWR_CORO_FIBER_DEAD: return ZEND_FIBER_STATUS_DEAD;
        case SWR_CORO_FIBER_FATAL:
            php_swoole_fatal_error(E_ERROR, "Unexpected state when get fiber status");
            return ZEND_FIBER_STATUS_DEAD;
        }
    }
''', r'''
    zend_fiber_context *from_context = from->fiber_context;
    zend_fiber_context *to_context = to->fiber_context;
    const auto cells = php_coroutine_metadata_cells(to);
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_FIBER, &cells, observation, 0).action) {
        case SWR_CORO_FIBER_DONE: return;
        case SWR_CORO_FIBER_FROM_STATUS: from_context->status = fiber_get_status(from); break;
        case SWR_CORO_FIBER_TO_STATUS: to_context->status = fiber_get_status(to); break;
        case SWR_CORO_FIBER_TEMP_INIT: to_context->status = ZEND_FIBER_STATUS_INIT; break;
        case SWR_CORO_FIBER_NOTIFY: zend_observer_fiber_switch_notify(from_context, to_context); break;
        case SWR_CORO_FIBER_REFRESH_STATUS: to_context->status = fiber_get_status(to); break;
        }
    }
''', r'''
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_fiber(&stage, SWR_CORO_FIBER_TRY, observation, nullptr)) {
        case SWR_CORO_FIBER_DONE: return;
        case SWR_CORO_FIBER_FROM_PRESENT: observation = from->fiber_context != nullptr; break;
        case SWR_CORO_FIBER_TO_PRESENT: observation = to->fiber_context != nullptr; break;
        case SWR_CORO_FIBER_SWITCH_NOTIFY: fiber_context_switch_notify(from, to); break;
        }
    }
''', r'''
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_fiber(&stage, SWR_CORO_FIBER_DESTROY, observation, nullptr)) {
        case SWR_CORO_FIBER_DONE: return;
        case SWR_CORO_FIBER_DESTROY_PRESENT: observation = ctx->fiber_context != nullptr; break;
        case SWR_CORO_FIBER_PUBLISH_DEAD: ctx->fiber_context->status = ZEND_FIBER_STATUS_DEAD; break;
        case SWR_CORO_FIBER_DESTROY_SWITCH: fiber_context_switch_try_notify(ctx, origin_ctx); break;
        case SWR_CORO_FIBER_DESTROY_NOTIFY: zend_observer_fiber_destroy_notify(ctx->fiber_context); break;
        case SWR_CORO_FIBER_REFRESH_PRESENT: observation = ctx->fiber_context != nullptr; break;
        case SWR_CORO_FIBER_FREE: efree(ctx->fiber_context); break;
        }
    }
''']
    for signature, replacement in zip(SIGNATURES, replacements):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
