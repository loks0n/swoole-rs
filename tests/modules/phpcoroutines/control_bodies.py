"""Cancellation/timeout frontend ordering; all Native Zend/core/timer effects stay Native."""
SIGNATURES = ['static bool php_swoole_coroutine_throw_exception(long cid, bool throw_exception, zend_class_entry *ce) {',
              'static PHP_METHOD(swoole_coroutine, setTimeLimit) {']


def replace_controls(source, result, body):
    signature = SIGNATURES[0]
    original = body(source, signature)
    replacement = r'''
    PHPContext *task = nullptr;
    Coroutine *co = nullptr;
    zend_object *previous = nullptr;
    zend_execute_data *ex_backup = nullptr;
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_control(&stage, static_cast<uint32_t>(throw_exception), observation, 0);
        switch (plan.action) {
        case SWR_CORO_CONTROL_FALSE: return false;
        case SWR_CORO_CONTROL_TRUE: return true;
        case SWR_CORO_CONTROL_TASK:
            task = PHPCoroutine::get_context_by_cid(cid);
            observation = task != nullptr;
            break;
        case SWR_CORO_CONTROL_COROUTINE:
            co = swoole_coroutine_get(cid);
            observation = co != nullptr;
            break;
        case SWR_CORO_CONTROL_MISSING: swoole_set_last_error(SW_ERROR_CO_NOT_EXISTS); break;
        case SWR_CORO_CONTROL_EXCEPTION: observation = task->exception != nullptr; break;
        case SWR_CORO_CONTROL_CLASS: observation = task->exception_class == ce; break;
        case SWR_CORO_CONTROL_CANCELED: swoole_set_last_error(SW_ERROR_CO_CANCELED); break;
        case SWR_CORO_CONTROL_ALLOCATE:
            previous = task->exception;
            task->exception_class = ce;
            task->exception = zend_objects_new(task->exception_class);
            object_properties_init(task->exception, task->exception_class);
            break;
        case SWR_CORO_CONTROL_PREVIOUS: observation = previous != nullptr; break;
        case SWR_CORO_CONTROL_LINK_PREVIOUS: zend_exception_set_previous(task->exception, previous); break;
        case SWR_CORO_CONTROL_SAVE_EXECUTOR:
            ex_backup = EG(current_execute_data);
            EG(current_execute_data) = task->execute_data;
            break;
        case SWR_CORO_CONTROL_FILE:
            zend::object_set(task->exception, ZSTR_KNOWN(ZEND_STR_FILE), zend_get_executed_filename_ex());
            break;
        case SWR_CORO_CONTROL_LINE:
            zend::object_set(task->exception, ZSTR_KNOWN(ZEND_STR_LINE), zend_get_executed_lineno());
            break;
        case SWR_CORO_CONTROL_RESTORE_EXECUTOR: EG(current_execute_data) = ex_backup; break;
        case SWR_CORO_CONTROL_CANCEL_IGNORE:
            // Ignore the result exactly as Native throw-exception mode does.
            task->co->cancel();
            break;
        case SWR_CORO_CONTROL_CANCEL_RESULT: observation = co->cancel(); break;
        }
    }
'''
    # Each preserved external effect must still be from the pinned body.
    for statement in ['task->exception_class = ce;', 'task->exception = zend_objects_new(task->exception_class);',
                      'object_properties_init(task->exception, task->exception_class);',
                      'zend_exception_set_previous(task->exception, previous);',
                      'EG(current_execute_data) = task->execute_data;', 'EG(current_execute_data) = ex_backup;',
                      'task->co->cancel();']:
        if statement not in original:
            raise ValueError('Pinned cancellation effect changed')
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    signature = SIGNATURES[1]
    original = body(source, signature)
    prefix = original[:original.index('    if (timeout == 0 || co == nullptr) {')]
    replacement = prefix + r'''    long cid = 0;
    uint32_t stage = 0;
    int64_t observation = co != nullptr;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_TIME_LIMIT, observation, timeout);
        switch (plan.action) {
        case SWR_CORO_CONTROL_FALSE: RETURN_FALSE;
        case SWR_CORO_CONTROL_TRUE: RETURN_TRUE;
        case SWR_CORO_CONTROL_CID: cid = co->get_cid(); break;
        case SWR_CORO_CONTROL_TIMER:
            swoole_timer_add(static_cast<long>(plan.value), false, [cid](swoole::Timer *, swoole::TimerNode *tnode) {
                swoole_timer_del(tnode);
                uint32_t callback_stage = 0;
                const int64_t present = PHPCoroutine::get_context_by_cid(cid) != nullptr;
                for (;;) {
                    const auto callback = swr_v1_phpcoroutines_control(&callback_stage, SWR_CORO_CONTROL_TIMEOUT_CALLBACK, present, 0);
                    switch (callback.action) {
                    case SWR_CORO_CONTROL_DONE: return;
                    case SWR_CORO_CONTROL_THROW_TIMEOUT:
                        php_swoole_coroutine_throw_exception(cid, true, swoole_coroutine_timeout_exception_ce);
                        break;
                    }
                }
            });
            break;
        }
    }
'''
    return result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
