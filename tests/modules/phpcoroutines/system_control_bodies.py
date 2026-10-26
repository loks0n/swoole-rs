"""Whole remaining System post-parse policy, keeping native IO/Zend custody."""
SIGNATURES = ['PHP_METHOD(swoole_coroutine_system, exec) {',
    'static void swoole_coroutine_system_wait(INTERNAL_FUNCTION_PARAMETERS, pid_t pid, double timeout) {',
    'PHP_METHOD(swoole_coroutine_system, waitSignal) {',
    'PHP_METHOD(swoole_coroutine_system, waitEvent) {']


