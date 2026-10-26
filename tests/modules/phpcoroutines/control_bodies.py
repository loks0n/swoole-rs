"""Cancellation/timeout frontend ordering; all Native Zend/core/timer effects stay Native."""
SIGNATURES = ['static bool php_swoole_coroutine_throw_exception(long cid, bool throw_exception, zend_class_entry *ce) {',
              'static PHP_METHOD(swoole_coroutine, setTimeLimit) {']


def replace_controls(source, result, body):
    signature = SIGNATURES[0]
    original = body(source, signature)
    replacement = r'''
    PHPContext *task = nullptr;
    Coroutine *co = nullptr;
    zend_object *exception = nullptr;
    zend_object *previous = nullptr;
    zend_execute_data *ex_backup = nullptr;
    zend_string *filename = nullptr;
    bool is_current = false;
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_control(&stage, static_cast<uint32_t>(throw_exception), observation, 0);
        switch (plan.action) {
        case SWR_CORO_CONTROL_FALSE: return false;
        case SWR_CORO_CONTROL_TRUE: return true;
        case SWR_CORO_CONTROL_TASK:
            task = PHPCoroutine::get_context_by_cid(cid);
            // The main context has no coroutine and cannot be canceled.
            observation = task != nullptr && task->co != nullptr;
            is_current = observation && task->co == Coroutine::get_current();
            break;
        case SWR_CORO_CONTROL_COROUTINE:
            co = swoole_coroutine_get(cid);
            observation = co != nullptr;
            break;
        case SWR_CORO_CONTROL_MISSING: swoole_set_last_error(SW_ERROR_CO_NOT_EXISTS); break;
        case SWR_CORO_CONTROL_EXCEPTION: observation = !is_current && task->exception != nullptr; break;
        case SWR_CORO_CONTROL_CLASS: observation = task->exception_class == ce; break;
        case SWR_CORO_CONTROL_CANCELED: swoole_set_last_error(SW_ERROR_CO_CANCELED); break;
        case SWR_CORO_CONTROL_ALLOCATE:
            exception = zend_objects_new(ce);
            object_properties_init(exception, ce);
            // The live Co::cancel frame is internal, so Zend redirects the user caller when this call
            // returns; the saved context describes a stale frame and must not be written here.
            if (is_current) {
                filename = zend_get_executed_filename_ex();
                if (filename) {
                    zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_FILE), filename);
                    zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_LINE), zend_get_executed_lineno());
                }
                zval zexception;
                ZVAL_OBJ(&zexception, exception);
                zend_throw_exception_object(&zexception);
                return true;
            }
            previous = task->exception;
            task->exception_class = ce;
            task->exception = exception;
            break;
        case SWR_CORO_CONTROL_PREVIOUS: observation = previous != nullptr; break;
        case SWR_CORO_CONTROL_LINK_PREVIOUS: zend_exception_set_previous(exception, previous); break;
        case SWR_CORO_CONTROL_SAVE_EXECUTOR:
            ex_backup = EG(current_execute_data);
            EG(current_execute_data) = task->execute_data;
            break;
        case SWR_CORO_CONTROL_FILE:
            filename = zend_get_executed_filename_ex();
            if (filename) {
                zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_FILE), filename);
            }
            break;
        case SWR_CORO_CONTROL_LINE:
            if (filename) {
                zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_LINE), zend_get_executed_lineno());
            }
            break;
        case SWR_CORO_CONTROL_RESTORE_EXECUTOR:
            EG(current_execute_data) = ex_backup;
            // Mirrors zend_throw_exception_internal(): internal frames have no opline and Zend redirects
            // the caller when the call returns.
            if (!previous && task->execute_data->func && ZEND_USER_CODE(task->execute_data->func->type) &&
                task->execute_data->opline->opcode != ZEND_HANDLE_EXCEPTION) {
                task->opline_before_exception = task->execute_data->opline;
                task->execute_data->opline = EG(exception_op);
            }
            break;
        case SWR_CORO_CONTROL_CANCEL_IGNORE:
            // Ignore the result exactly as Native throw-exception mode does.
            task->co->cancel();
            break;
        case SWR_CORO_CONTROL_CANCEL_RESULT: observation = co->cancel(); break;
        }
    }
'''
    # Each preserved external effect must still be from the pinned body.
    for statement in ['zend_objects_new(ce);', 'object_properties_init(exception, ce);',
                      'zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_FILE), filename);',
                      'zend::object_set(exception, ZSTR_KNOWN(ZEND_STR_LINE), zend_get_executed_lineno());',
                      'zend_throw_exception_object(&zexception);', 'task->exception_class = ce;',
                      'task->exception = exception;', 'zend_exception_set_previous(exception, previous);',
                      'EG(current_execute_data) = task->execute_data;', 'EG(current_execute_data) = ex_backup;',
                      'task->opline_before_exception = task->execute_data->opline;',
                      'task->execute_data->opline = EG(exception_op);', 'task->co->cancel();']:
        if statement not in original or statement not in replacement:
            raise ValueError('Pinned cancellation effect changed')
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    signature = SIGNATURES[1]
    original = body(source, signature)
    prefix = original[:original.index('    if (sw_unlikely(timeout <= 0 || co == nullptr)) {')]
    replacement = prefix + r'''    long cid = 0;
    PHPContext *ctx = nullptr;
    uint32_t stage = 0;
    // Negative timeouts are rejected like a missing coroutine.
    int64_t observation = co != nullptr && timeout > 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_TIME_LIMIT, observation, timeout);
        switch (plan.action) {
        case SWR_CORO_CONTROL_FALSE: RETURN_FALSE;
        case SWR_CORO_CONTROL_TRUE: RETURN_TRUE;
        case SWR_CORO_CONTROL_CID:
            cid = co->get_cid();
            ctx = static_cast<PHPContext *>(co->get_task());
            break;
        case SWR_CORO_CONTROL_TIMER: {
            // Seconds keep their fractional precision; plan.value is the truncated legacy millisecond count.
            TimerNode *timer = swoole_timer_add(timeout, false, [cid](Timer *, TimerNode *) {
                PHPContext *ctx = PHPCoroutine::get_context_by_cid(cid);
                uint32_t callback_stage = 0;
                const int64_t present = ctx != nullptr;
                for (;;) {
                    const auto callback = swr_v1_phpcoroutines_control(&callback_stage, SWR_CORO_CONTROL_TIMEOUT_CALLBACK, present, 0);
                    switch (callback.action) {
                    case SWR_CORO_CONTROL_DONE: return;
                    case SWR_CORO_CONTROL_THROW_TIMEOUT:
                        ctx->timer_limit = nullptr;
                        php_swoole_coroutine_throw_exception(cid, true, swoole_coroutine_timeout_exception_ce);
                        break;
                    }
                }
            });
            if (sw_unlikely(!timer)) {
                RETURN_FALSE;
            }
            TimerNode *old = ctx->timer_limit;
            ctx->timer_limit = timer;
            if (old) {
                swoole_timer_del(old);
            }
            break;
        }
        }
    }
'''
    return result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
