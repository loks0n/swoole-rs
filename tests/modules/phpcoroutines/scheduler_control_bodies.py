"""Remaining Scheduler control, with Native effects and pointer custody exact."""
SIGNATURES = ['static bool php_swoole_coroutine_reactor_can_exit(Reactor *reactor, size_t &event_num) {',
              'void php_swoole_coroutine_scheduler_rshutdown() {',
              'PHP_METHOD(swoole_coroutine_scheduler, getOptions) {']


def replace_scheduler_controls(source, result, body):
    replacement = r'''
    zval retval{};
    const swr_phpcoroutines_scheduler_constants constants{SUCCESS, IS_FALSE, NameResolver::TYPE_PHP};
    swr_phpcoroutines_callback_control_state state{};
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_callback_control(&state, &exit_condition_fci_cache, SWR_CORO_SCHED_CONTROL_CALLBACK, observation, &constants);
        switch (plan.action) {
        case SWR_CORO_CALLBACK_ASSERT:
            SW_ASSERT(plan.identity);
            ZVAL_NULL(&retval);
            break;
        case SWR_CORO_SCHED_CONTROL_CALL:
            observation = sw_zend_call_function_ex(nullptr, reinterpret_cast<zend::Callable *>(plan.identity)->ptr(), 0, nullptr, &retval);
            break;
        case SWR_CORO_SCHED_CONTROL_FATAL:
            php_swoole_fatal_error(E_ERROR, "Coroutine can_exit callback handler error");
            break;
        case SWR_CORO_SCHED_CONTROL_EXCEPTION_PRESENCE: observation = EG(exception) != nullptr; break;
        case SWR_CORO_SCHED_CONTROL_EXCEPTION: zend_exception_error(EG(exception), E_ERROR); break;
        case SWR_CORO_SCHED_CONTROL_RESULT: observation = Z_TYPE_P(&retval); break;
        case SWR_CORO_SCHED_CONTROL_TRUE: return true;
        case SWR_CORO_SCHED_CONTROL_FALSE: return false;
        }
    }
'''
    shutdown = r'''
    swr_phpcoroutines_callback_control_state state{};
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_callback_control(&state, &exit_condition_fci_cache, SWR_CORO_SCHED_CONTROL_SHUTDOWN, observation, nullptr);
        switch (plan.action) {
        case SWR_CORO_SCHED_CONTROL_DONE: return;
        case SWR_CORO_SCHED_CONTROL_RESOLVERS:
            swoole_name_resolver_each([](const std::list<NameResolver>::iterator &iter) -> swTraverseOperation {
                const swr_phpcoroutines_scheduler_constants constants{SUCCESS, IS_FALSE, NameResolver::TYPE_PHP};
                uint32_t resolver_stage = 0;
                const int64_t type = iter->type;
                for (;;) {
                    switch (swr_v1_phpcoroutines_scheduler_control(&resolver_stage, SWR_CORO_SCHED_CONTROL_RESOLVER, type, &constants)) {
                    case SWR_CORO_SCHED_CONTROL_RESOLVER_DTOR: zval_dtor((zval *) iter->private_data); break;
                    case SWR_CORO_SCHED_CONTROL_RESOLVER_FREE: efree(iter->private_data); break;
                    case SWR_CORO_SCHED_CONTROL_KEEP: return SW_TRAVERSE_KEEP;
                    case SWR_CORO_SCHED_CONTROL_REMOVE: return SW_TRAVERSE_REMOVE;
                    }
                }
            });
            break;
        case SWR_CORO_SCHED_CONTROL_CACHE_FREE: sw_callable_free(reinterpret_cast<zend::Callable *>(plan.identity)); break;
        }
    }
'''
    options = r'''
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_scheduler_control(&stage, SWR_CORO_SCHED_CONTROL_OPTIONS, observation, nullptr)) {
        case SWR_CORO_SCHED_CONTROL_DONE: return;
        case SWR_CORO_SCHED_CONTROL_OPTIONS_PRESENCE: observation = PHPCoroutine::options != nullptr; break;
        case SWR_CORO_SCHED_CONTROL_OPTIONS_DUP: RETURN_ARR(zend_array_dup(PHPCoroutine::options));
        }
    }
'''
    for signature, selected in zip(SIGNATURES, [replacement, shutdown, options]):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + selected + '#else' + original + '#endif\n}')
    return result
