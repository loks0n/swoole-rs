<?php
// Ordinary primitive configuration only; no frontend instances, callbacks, hooks,
// Coroutine/Event/IO or preemptive thread activation.
if (Swoole\Coroutine::getOptions() !== null) throw new RuntimeException('Unexpected initial options');
$observations = [];
foreach ([7, 19] as $limit) {
    $options = ['max_coro_num' => $limit, 'enable_deadlock_check' => false,
        'enable_preemptive_scheduler' => false, 'hook_flags' => 0];
    Swoole\Coroutine::set($options);
    $expected = ['hook_flags' => 0] + $options;
    if (Swoole\Coroutine::getOptions() !== $expected) throw new RuntimeException('Configuration publication differs');
    $observations[] = Swoole\Coroutine::getOptions();
}
$options = ['max_coro_num' => SWOOLE_DEFAULT_MAX_CORO_NUM, 'enable_deadlock_check' => true,
    'enable_preemptive_scheduler' => false, 'hook_flags' => 0];
Swoole\Coroutine::set($options);
$expected = ['hook_flags' => 0] + $options;
if (Swoole\Coroutine::getOptions() !== $expected) throw new RuntimeException('Configuration defaults restore differs');
$observations[] = Swoole\Coroutine::getOptions();
echo json_encode($observations, JSON_THROW_ON_ERROR), "\n";
