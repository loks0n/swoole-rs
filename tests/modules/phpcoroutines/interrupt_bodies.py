"""Whole interrupt custody; preserve Native scope, thread/VM/signal/clock effects."""
DECL = '    static SW_THREAD_LOCAL std::atomic_bool interrupt_thread_running;'
SELECTED_DECL = '''#ifdef SWOOLE_RS_PHPCOROUTINES
    static SW_THREAD_LOCAL swr_phpcoroutines_interrupt_state interrupt_thread_running;
#else
    static SW_THREAD_LOCAL std::atomic_bool interrupt_thread_running;
#endif'''
SIGNATURES = ['void PHPCoroutine::interrupt_thread_start() {', 'void PHPCoroutine::interrupt_thread_stop() {']


