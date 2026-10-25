"""Terminal/diagnostic decisions only; all Native effects execute after Rust returns."""
SIGNATURES = ['bool PHPCoroutine::catch_exception() {',
              'void PHPCoroutine::deadlock_check() {',
              'void PHPCoroutine::on_close(void *arg) {']


def replace_terminal(source, result, body):
    diagnostic = body(body(source, SIGNATURES[1]), 'else {')
    replacements = [r'''
    uint32_t stage = 0;
    int64_t observation = 0;
#if SW_RECOVER_CANCELED_EXCEPTION
    constexpr uint32_t kind = SWR_CORO_CONTROL_CATCH_RECOVER;
#else
    constexpr uint32_t kind = SWR_CORO_CONTROL_CATCH;
#endif
    for (;;) {
        switch (swr_v1_phpcoroutines_control(&stage, kind, observation, 0).action) {
        case SWR_CORO_CONTROL_FALSE: return false;
        case SWR_CORO_CONTROL_TRUE: return true;
        case SWR_CORO_CONTROL_EXCEPTION: observation = EG(exception) != nullptr; break;
#if SW_RECOVER_CANCELED_EXCEPTION
        case SWR_CORO_CONTROL_CLASS: observation = EG(exception)->ce == swoole_coroutine_canceled_exception_ce; break;
        case SWR_CORO_CONTROL_RELEASE_EXCEPTION: OBJ_RELEASE(EG(exception)); break;
        case SWR_CORO_CONTROL_CLEAR_EXCEPTION: EG(exception) = nullptr; break;
#endif
        case SWR_CORO_CONTROL_FATAL_EXCEPTION:
            // the exception error messages MUST be output on the current coroutine stack
            zend_exception_error(EG(exception), E_ERROR);
            break;
        }
    }
''', r'''
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_DEADLOCK, observation, 0).action) {
        case SWR_CORO_CONTROL_DONE: return;
        case SWR_CORO_CONTROL_CORE_COUNT: observation = Coroutine::count() != 0; break;
        case SWR_CORO_CONTROL_FATAL_PRESENCE: observation = php_swoole_is_fatal_error(); break;
        case SWR_CORO_CONTROL_REACTOR_PRESENCE: observation = sw_reactor() != nullptr; break;
        case SWR_CORO_CONTROL_REACTOR_BAILOUT: observation = sw_reactor()->bailout; break;
        case SWR_CORO_CONTROL_LIBRARY_PRESENCE: observation = SWOOLE_G(enable_library); break;
        case SWR_CORO_CONTROL_LIBRARY_DIAGNOSTIC:
            zend::function::call(R"(\Swoole\Coroutine\deadlock_check)", 0, nullptr);
            break;
        case SWR_CORO_CONTROL_PRINT_DIAGNOSTIC: {
''' + diagnostic + r'''
            break;
        }
        }
    }
''', r'''
    auto *ctx = static_cast<PHPContext *>(arg);
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_control(&stage, SWR_CORO_CONTROL_CLOSE, observation, 0).action) {
        case SWR_CORO_CONTROL_DONE: return;
        case SWR_CORO_CONTROL_CLOSE_PRESENCE: observation = ctx->on_close != nullptr; break;
        case SWR_CORO_CONTROL_CLOSE_CALLBACK: (*ctx->on_close)(ctx); break;
        case SWR_CORO_CONTROL_CLOSE_FREE: efree(ctx); break;
        }
    }
''']
    for signature, replacement in zip(SIGNATURES, replacements):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
