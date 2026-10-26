"""Remaining Scheduler control, with Native effects and pointer custody exact."""
SIGNATURES = ['static bool php_swoole_coroutine_reactor_can_exit(Reactor *reactor, size_t &event_num) {',
              'void php_swoole_coroutine_scheduler_rshutdown() {',
              'PHP_METHOD(swoole_coroutine_scheduler, getOptions) {']


