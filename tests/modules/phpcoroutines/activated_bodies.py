"""Whole activated-state custody; original Native scope/seed/effects remain."""
ACTIVATED_DECL = '    static SW_THREAD_LOCAL bool activated;'
ACTIVATED_SELECTED_DECL = '''#ifdef SWOOLE_RS_PHPCOROUTINES
    static SW_THREAD_LOCAL swr_phpcoroutines_activation_state activated;
#else
    static SW_THREAD_LOCAL bool activated;
#endif'''
ACTIVATED_SIGNATURE = 'static inline bool is_activated() {'


def replace_activated_header(source, result, body):
    # These old ACTIVE route calls are the identity predicate. The sole Rust
    # phase read now supplies that decision directly; avoid a second FFI hop.
    for signature in ['static inline long get_cid() {',
                      'static inline long get_elapsed(long cid = 0) {',
                      'static inline long get_execute_time(long cid = 0) {']:
        before = body(result, signature)
        active, fallback = before.split('#else', 1)
        active = active.replace('swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)', 'is_activated()')
        result = result.replace(signature + before + '}', signature + active + '#else' + fallback + '}')
    original = body(source, ACTIVATED_SIGNATURE)
    result = result.replace(ACTIVATED_SIGNATURE + original + '}', ACTIVATED_SIGNATURE + '''
#ifdef SWOOLE_RS_PHPCOROUTINES
        return swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_READ);
#else''' + original + '#endif\n    }')
    return result.replace(ACTIVATED_DECL, ACTIVATED_SELECTED_DECL)


def replace_activated_cpp(source, result, body):
    original_seed = 'SW_THREAD_LOCAL bool PHPCoroutine::activated = false;'
    if original_seed not in source:
        raise ValueError('Pinned activated constant seed changed')
    result = result.replace(original_seed, '''#ifdef SWOOLE_RS_PHPCOROUTINES
SW_THREAD_LOCAL swr_phpcoroutines_activation_state PHPCoroutine::activated{0};
#else
''' + original_seed + '\n#endif')
    for signature in ['void PHPCoroutine::activate() {',
                      'void PHPCoroutine::deactivate(void *ptr) {',
                      'long PHPCoroutine::create(zend_fcall_info_cache *fci_cache, uint32_t argc, zval *argv, zval *callable) {']:
        before = body(result, signature)
        active, fallback = before.split('#else', 1)
        active = active.replace('observation = activated;', 'observation = is_activated();')
        active = active.replace('if (sw_unlikely(!activated))', 'if (sw_unlikely(!is_activated()))')
        active = active.replace('activated = true;', 'swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_START);')
        active = active.replace('activated = false;', 'swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_STOP);')
        result = result.replace(signature + before + '}', signature + active + '#else' + fallback + '}')
    signature = 'void PHPCoroutine::shutdown() {'
    original = body(source, signature)
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' +
                            original.replace('if (activated)', 'if (is_activated())') + '#else' + original + '#endif\n}')
    return result
