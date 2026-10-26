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


