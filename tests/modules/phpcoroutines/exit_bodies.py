"""Both versioned exit frontends; Zend payloads/termination stay Native."""
SIGNATURES = ['static int coro_exit_handler(zend_execute_data *execute_data) {',
              'PHP_FUNCTION(swoole_exit) {']


def replace_exits(source, result, body):
    for kind, signature in enumerate(SIGNATURES):
        original = body(source, signature)
        replacement = ('\n    zval ex{};\n' if kind == 0 else '\n') + '''    const swr_phpcoroutines_exit_config config{
        SW_EXIT_IN_COROUTINE, SW_EXIT_IN_SERVER, IS_UNUSED, IS_CONST};
    swr_phpcoroutines_exit_state state{};
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_exit(&state, &config, ''' + str(kind) + ''', observation);
        switch (plan.action) {
        case SWR_CORO_EXIT_CURRENT: observation = Coroutine::get_current() != nullptr; break;
        case SWR_CORO_EXIT_SERVER: observation = sw_server() != nullptr; break;
        case SWR_CORO_EXIT_SERVER_STARTED: observation = sw_server()->is_started(); break;
'''
        if kind == 0:
            const = body(original, 'if (opline->op1_type == IS_CONST) {')
            replacement += '''        case SWR_CORO_EXIT_DONE: return ZEND_USER_OPCODE_DISPATCH;
        case SWR_CORO_EXIT_LEGACY_BEGIN: {
            const zend_op *opline = EX(opline);
            zval _exit_status{};
            zval *exit_status = nullptr;
            for (;;) {
                const auto part = swr_v1_phpcoroutines_exit(&state, &config, 0, observation);
                switch (part.action) {
                case SWR_CORO_EXIT_DONE: return ZEND_USER_OPCODE_DISPATCH;
                case SWR_CORO_EXIT_OPERAND: observation = opline->op1_type; break;
                case SWR_CORO_EXIT_CONSTANT: {
''' + const + '''                    break;
                }
                case SWR_CORO_EXIT_VARIABLE: exit_status = EX_VAR(opline->op1.var); break;
                case SWR_CORO_EXIT_NULL:
                    exit_status = &_exit_status;
                    ZVAL_NULL(exit_status);
                    break;
                case SWR_CORO_EXIT_REFERENCE: observation = Z_ISREF_P(exit_status); break;
                case SWR_CORO_EXIT_UNWRAP: exit_status = Z_REFVAL_P(exit_status); break;
                case SWR_CORO_EXIT_DUP:
                    ZVAL_DUP(&_exit_status, exit_status);
                    exit_status = &_exit_status;
                    break;
                case SWR_CORO_EXIT_THROW_LEGACY: {
                    zend_object *obj = zend_throw_exception(swoole_exit_exception_ce, "swoole exit", 0);
                    ZVAL_OBJ(&ex, obj);
                    break;
                }
                case SWR_CORO_EXIT_FLAGS:
                    zend_update_property_long(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("flags"), part.flags);
                    break;
                case SWR_CORO_EXIT_LEGACY_STATUS:
                    Z_TRY_ADDREF_P(exit_status);
                    zend_update_property(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("status"), exit_status);
                    break;
                }
            }
        }
'''
        else:
            replacement += '''        case SWR_CORO_EXIT_DONE: return;
        case SWR_CORO_EXIT_MODERN_BEGIN: {
            zend_string *message = NULL;
            zend_long status = 0;

            ZEND_PARSE_PARAMETERS_START(0, 1)
            Z_PARAM_OPTIONAL
            Z_PARAM_STR_OR_LONG(message, status)
            ZEND_PARSE_PARAMETERS_END();

            zval ex = {};
            for (;;) {
                const auto part = swr_v1_phpcoroutines_exit(&state, &config, 1, observation);
                switch (part.action) {
                case SWR_CORO_EXIT_DONE: return;
                case SWR_CORO_EXIT_MESSAGE: observation = message != nullptr; break;
                case SWR_CORO_EXIT_THROW_MESSAGE: {
                    zend_object *obj = zend_throw_exception(swoole_exit_exception_ce, ZSTR_VAL(message), 0);
                    ZVAL_OBJ(&ex, obj);
                    break;
                }
                case SWR_CORO_EXIT_THROW_DEFAULT: {
                    zend_object *obj = zend_throw_exception(swoole_exit_exception_ce, "swoole exit", 0);
                    ZVAL_OBJ(&ex, obj);
                    break;
                }
                case SWR_CORO_EXIT_FLAGS:
                    zend_update_property_long(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("flags"), part.flags);
                    break;
                case SWR_CORO_EXIT_STATUS_STRING:
                    zend_update_property_str(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("status"), message);
                    break;
                case SWR_CORO_EXIT_STATUS_LONG:
                    zend_update_property_long(swoole_exit_exception_ce, SW_Z8_OBJ_P(&ex), ZEND_STRL("status"), status);
                    break;
                case SWR_CORO_EXIT_ORIGINAL:
                    observation = php_swoole_call_original_handler(ZEND_STRL("exit"), INTERNAL_FUNCTION_PARAM_PASSTHRU);
                    break;
                case SWR_CORO_EXIT_WRITE: php_write(ZSTR_VAL(message), ZSTR_LEN(message)); break;
                case SWR_CORO_EXIT_NATIVE: sw_php_exit(status); return;
                }
            }
        }
'''
        replacement += '        }\n    }\n'
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
