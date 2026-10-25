"""Request/creation lifecycle policy; native Zend/callback/bailout effects retained."""
SIGNATURES = ['PHP_FUNCTION(swoole_coroutine_create) {',
              'void php_swoole_coroutine_rshutdown() {',
              'void PHPCoroutine::bailout() {']


def replace_lifecycle(source, result, body):
    original = body(source, SIGNATURES[0])
    if original.count('memcmp(ZSTR_VAL(func->common.function_name), ZEND_STRS("__destruct")) == 0') != 1:
        raise ValueError('Pinned ten-byte destructor predicate changed')
    prefix = original[:original.index('    if (sw_unlikely(SWOOLE_G(req_status)')]
    replacements = [prefix + r'''    zend_function *func = nullptr;
    long cid = 0;
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_CREATE_FRONTEND, observation, 0).action) {
        case SWR_CORO_CONTROL_FALSE: RETURN_FALSE;
        case SWR_CORO_CONTROL_CREATE_LONG: RETURN_LONG(cid);
        case SWR_CORO_CONTROL_REQUEST_SHUTDOWN:
            observation = SWOOLE_G(req_status) == PHP_SWOOLE_CALL_USER_SHUTDOWNFUNC_BEGIN;
            break;
        case SWR_CORO_CONTROL_CALLER_FUNCTION: func = EG(current_execute_data)->prev_execute_data->func; break;
        case SWR_CORO_CONTROL_CALLER_NAME: observation = func->common.function_name != nullptr; break;
        case SWR_CORO_CONTROL_CALLER_DESTRUCTOR:
            observation = swr_v1_phpcoroutines_create_destructor(reinterpret_cast<const uint8_t *>(ZSTR_VAL(func->common.function_name)));
            break;
        case SWR_CORO_CONTROL_CREATE_FATAL:
            php_swoole_fatal_error(E_ERROR, "can not use coroutine in __destruct after php_request_shutdown");
            break;
        case SWR_CORO_CONTROL_CREATE_EFFECT:
            cid = PHPCoroutine::create(&fci_cache, fci.param_count, fci.params, &fci.function_name);
            observation = cid;
            break;
        }
    }
''', r'''
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_REQUEST_SHUTDOWN_FRONTEND, observation, 0).action) {
        case SWR_CORO_CONTROL_DONE: return;
        case SWR_CORO_CONTROL_AUTOLOAD_PRESENCE: observation = SWOOLE_G(in_autoload) != nullptr; break;
        case SWR_CORO_CONTROL_AUTOLOAD_DESTROY: zend_hash_destroy(SWOOLE_G(in_autoload)); break;
        case SWR_CORO_CONTROL_AUTOLOAD_FREE: FREE_HASHTABLE(SWOOLE_G(in_autoload)); break;
        case SWR_CORO_CONTROL_AUTOLOAD_CLEAR: SWOOLE_G(in_autoload) = nullptr; break;
        case SWR_CORO_CONTROL_REQUEST_STOP: PHPCoroutine::shutdown(); break;
        }
    }
''', r'''
    Coroutine::bailout([]() {
        uint32_t stage = 0;
        int64_t observation = 0;
        for (;;) {
            switch (swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_BAILOUT, observation, 0).action) {
            case SWR_CORO_CONTROL_DONE: return;
            case SWR_CORO_CONTROL_REACTOR_PRESENCE: observation = sw_reactor() != nullptr; break;
            case SWR_CORO_CONTROL_REACTOR_STOP: sw_reactor()->running = false; break;
            case SWR_CORO_CONTROL_REACTOR_BAILOUT_PUBLISH: sw_reactor()->bailout = true; break;
            case SWR_CORO_CONTROL_ZEND_BAILOUT: zend_bailout(); break;
            }
        }
    });
''']
    for signature, replacement in zip(SIGNATURES, replacements):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
