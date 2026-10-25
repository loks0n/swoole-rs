"""Whole primitive Config custody, preserving public Config and native fallback."""
CONFIG_SIGNATURES = ['static inline uint64_t get_max_num() {',
    'static inline void set_max_num(uint64_t n) {',
    'static inline void set_deadlock_check(bool value = true) {',
    'static inline uint32_t get_hook_flags() {',
    'static inline void enable_preemptive_scheduler(bool value) {']
CONFIG_DECL = '    static SW_THREAD_LOCAL Config config;'
CONFIG_SELECTED_DECL = '''#ifdef SWOOLE_RS_PHPCOROUTINES
    static SW_THREAD_LOCAL swr_phpcoroutines_config_state config;
#else
    static SW_THREAD_LOCAL Config config;
#endif'''


def replace_config_header(source, result, body):
    effects = ['return swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_MAX, 0);',
        'swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_MAX, n);',
        'swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_DEADLOCK, value);',
        'return static_cast<uint32_t>(swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_HOOKS, 0));',
        'swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_PREEMPTIVE, value);']
    for signature, effect in zip(CONFIG_SIGNATURES, effects):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n        ' + effect + '\n#else' + original + '#endif\n    }')
    return result.replace(CONFIG_DECL, CONFIG_SELECTED_DECL)


def replace_config_cpp(source, result, body):
    original = '''SW_THREAD_LOCAL PHPCoroutine::Config PHPCoroutine::config{
    SW_DEFAULT_MAX_CORO_NUM,
    0,
    false,
    true,
};'''
    selected = '''SW_THREAD_LOCAL swr_phpcoroutines_config_state PHPCoroutine::config{
    SW_DEFAULT_MAX_CORO_NUM, 0, 0, 0,
};'''
    if original not in source:
        raise ValueError('Pinned constant Config seed changed')
    result = result.replace(original, '#ifdef SWOOLE_RS_PHPCOROUTINES\n' + selected + '\n#else\n' + original + '\n#endif')
    for signature, old, new in [
        ('void PHPCoroutine::deactivate(void *ptr) {', 'config.enable_deadlock_check',
         'swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_DEADLOCK, 0)'),
        ('void PHPCoroutine::set_hook_flags(uint32_t flags) {', 'config.hook_flags = flags;',
         'swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_HOOKS, flags);')]:
        original = body(source, signature)
        if old not in original:
            raise ValueError('Pinned Config caller changed')
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' + original.replace(old, new) + '#else' + original + '#endif\n}')
    return result
