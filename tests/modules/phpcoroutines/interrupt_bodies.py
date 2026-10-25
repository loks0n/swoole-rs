"""Whole interrupt custody; preserve Native scope, thread/VM/signal/clock effects."""
DECL = '    static SW_THREAD_LOCAL bool interrupt_thread_running;'
SELECTED_DECL = '''#ifdef SWOOLE_RS_PHPCOROUTINES
    static SW_THREAD_LOCAL swr_phpcoroutines_interrupt_state interrupt_thread_running;
#else
    static SW_THREAD_LOCAL bool interrupt_thread_running;
#endif'''
SIGNATURES = ['void PHPCoroutine::interrupt_thread_start() {', 'void PHPCoroutine::interrupt_thread_stop() {']


def replace_interrupt_header(source, result, body):
    if source.count(DECL) != 1: raise ValueError('Pinned interrupt declaration changed')
    return result.replace(DECL, SELECTED_DECL)


def replace_interrupt_cpp(source, result, body):
    seed = 'SW_THREAD_LOCAL bool PHPCoroutine::interrupt_thread_running = false;'
    if source.count(seed) != 1: raise ValueError('Pinned interrupt scope/seed changed')
    result = result.replace(seed, '''#ifdef SWOOLE_RS_PHPCOROUTINES
SW_THREAD_LOCAL swr_phpcoroutines_interrupt_state PHPCoroutine::interrupt_thread_running{0};
#else
''' + seed + '\n#endif')
    replacements = [r'''
    uint32_t stage = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_interrupt(&interrupt_thread_running, &stage, SWR_CORO_INTERRUPT_START, MAX_EXEC_MSEC);
        switch (plan.action) {
        case SWR_CORO_INTERRUPT_DONE: return;
        case SWR_CORO_INTERRUPT_VM_CAPTURE: zend_vm_interrupt = &EG(vm_interrupt); break;
        case SWR_CORO_INTERRUPT_THREAD_START:
            interrupt_thread = std::thread([]() {
                swoole_signal_block_all();
                uint32_t child_stage = 0;
                for (;;) {
                    const auto child = swr_v1_phpcoroutines_interrupt(&interrupt_thread_running, &child_stage, SWR_CORO_INTERRUPT_CHILD, MAX_EXEC_MSEC);
                    switch (child.action) {
                    case SWR_CORO_INTERRUPT_DONE: return;
                    case SWR_CORO_INTERRUPT_VM_STORE: zend_atomic_bool_store(zend_vm_interrupt, 1); break;
                    case SWR_CORO_INTERRUPT_SLEEP:
                        std::this_thread::sleep_for(std::chrono::milliseconds(child.value));
                        break;
                    }
                }
            });
            break;
        }
    }
''', r'''
    uint32_t stage = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_interrupt(&interrupt_thread_running, &stage, SWR_CORO_INTERRUPT_STOP, MAX_EXEC_MSEC);
        switch (plan.action) {
        case SWR_CORO_INTERRUPT_DONE: return;
        case SWR_CORO_INTERRUPT_THREAD_JOIN: interrupt_thread.join(); break;
        }
    }
''']
    for signature, replacement in zip(SIGNATURES, replacements):
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
