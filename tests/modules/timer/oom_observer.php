<?php
// The unchanged failing bailout fixture remains separate. This observer has a native budget.
[$script, $library, $mode] = $argv;
$ffi = FFI::cdef('int swr_timer_oom_arm(long id, unsigned int budget);', $library);
swoole_async_set(['enable_coroutine' => false]);
register_shutdown_function(static function () {
    echo 'SHUTDOWN ', error_get_last()['type'] ?? 0, "\n";
});
if ($mode === 'oom') ini_set('memory_limit', (string)(memory_get_usage(true) + 1024 * 1024));
$id = Swoole\Timer::tick(1, static function () use ($mode) {
    echo "CALL\n";
    if ($mode === 'oom') $blob = str_repeat('x', 32 * 1024 * 1024);
});
if ($ffi->swr_timer_oom_arm($id, 8) !== 0) throw new RuntimeException('Cannot arm observer');
Swoole\Event::wait();
echo "RETURN\n";
