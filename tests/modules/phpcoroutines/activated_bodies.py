"""Whole activated-state custody; original Native scope/seed/effects remain."""
ACTIVATED_DECL = '    static SW_THREAD_LOCAL bool activated;'
ACTIVATED_SELECTED_DECL = '''#ifdef SWOOLE_RS_PHPCOROUTINES
    static SW_THREAD_LOCAL swr_phpcoroutines_activation_state activated;
#else
    static SW_THREAD_LOCAL bool activated;
#endif'''
ACTIVATED_SIGNATURE = 'static inline bool is_activated() {'


