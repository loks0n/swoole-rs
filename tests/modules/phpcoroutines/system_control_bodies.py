"""Whole remaining System post-parse policy, keeping native IO/Zend custody."""
SIGNATURES = ['PHP_METHOD(swoole_coroutine_system, exec) {',
    'static void swoole_coroutine_system_wait(INTERNAL_FUNCTION_PARAMETERS, pid_t pid, double timeout) {',
    'PHP_METHOD(swoole_coroutine_system, waitSignal) {',
    'PHP_METHOD(swoole_coroutine_system, waitEvent) {']


def replace_system_controls(source, result, body):
    replacements = []
    original = body(source, SIGNATURES[0])
    prefix = original[:original.index('    if (!System::exec(')]
    custody = original[original.index('    auto str ='):original.index('    array_init(return_value);')]
    replacements.append(prefix + '''    int64_t observation = System::exec(command, get_error_stream, buffer, &status);
    swr_phpcoroutines_result_state state{};
    auto admitted = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_EXEC, &state, observation, 0);
    if (admitted.action == SWR_CORO_RESULT_FALSE) {
        RETURN_FALSE;
    }
''' + custody + '''
    for (;;) {
        auto plan = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_EXEC, &state, observation, 0);
        switch (plan.action) {
        case SWR_CORO_RESULT_DONE: return;
        case SWR_CORO_RESULT_FALSE: RETURN_FALSE;
        case SWR_CORO_RESULT_ARRAY: array_init(return_value); break;
        case SWR_CORO_RESULT_FIELD:
            switch (plan.index) {
            case 0: add_assoc_long(return_value, plan.key, WEXITSTATUS(status)); break;
            case 1: add_assoc_long(return_value, plan.key, WTERMSIG(status)); break;
            case 2: add_assoc_zval(return_value, plan.key, &zdata); break;
            }
            break;
        }
    }
''')
    original = body(source, SIGNATURES[1])
    prefix = original[:original.index('    if (pid < 0) {')]
    replacements.append(prefix + '''    int64_t observation = pid;
    swr_phpcoroutines_result_state state{};
    for (;;) {
        auto plan = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WAIT, &state, observation, 0);
        switch (plan.action) {
        case SWR_CORO_RESULT_DONE: return;
        case SWR_CORO_RESULT_FALSE: RETURN_FALSE;
        case SWR_CORO_RESULT_WAIT_ANY: pid = System::wait(&status, timeout); observation = pid; break;
        case SWR_CORO_RESULT_WAIT_PID: pid = System::waitpid(pid, &status, 0, timeout); observation = pid; break;
        case SWR_CORO_RESULT_ARRAY: array_init(return_value); break;
        case SWR_CORO_RESULT_FIELD:
            switch (plan.index) {
            case 0: add_assoc_long(return_value, plan.key, pid); break;
            case 1: add_assoc_long(return_value, plan.key, WEXITSTATUS(status)); break;
            case 2: add_assoc_long(return_value, plan.key, WTERMSIG(status)); break;
            }
            break;
        }
    }
''')
    original = body(source, SIGNATURES[2])
    prefix = original[:original.index('    if (signo == -1) {')]
    replacements.append(prefix + '''    int64_t observation = signo;
    swr_phpcoroutines_result_state state{};
    for (;;) {
        auto plan = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &state, observation, 0);
        switch (plan.action) {
        case SWR_CORO_RESULT_FALSE: RETURN_FALSE;
        case SWR_CORO_RESULT_LONG: RETURN_LONG(signo);
        case SWR_CORO_RESULT_BUSY: observation = swoole_get_last_error() == EBUSY; break;
        case SWR_CORO_RESULT_INVALID: observation = swoole_get_last_error() == EINVAL; break;
        case SWR_CORO_RESULT_WARN_BUSY:
            php_swoole_fatal_error(E_WARNING, "Unable to wait signal, async signal listener has been registered");
            break;
        case SWR_CORO_RESULT_WARN_INVALID:
            php_swoole_fatal_error(E_WARNING, "Invalid signal in the given list");
            break;
        case SWR_CORO_RESULT_ERRNO: errno = swoole_get_last_error(); break;
        }
    }
''')
    original = body(source, SIGNATURES[3])
    prefix = original[:original.index('    if (fd < 0) {')]
    replacements.append(prefix + '''    int64_t observation = fd;
    swr_phpcoroutines_result_state state{};
    for (;;) {
        auto plan = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_EVENT, &state, observation, 0);
        switch (plan.action) {
        case SWR_CORO_RESULT_BAD_FD:
            php_swoole_fatal_error(E_WARNING, "unknown fd type");
            RETURN_FALSE;
        case SWR_CORO_RESULT_EVENT_WAIT: events = System::wait_event(fd, events, timeout); observation = events; break;
        case SWR_CORO_RESULT_FALSE: RETURN_FALSE;
        case SWR_CORO_RESULT_LONG: RETURN_LONG(events);
        }
    }
''')
    for signature, replacement in zip(SIGNATURES, replacements):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
