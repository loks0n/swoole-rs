<?php
// Ordinary read-only frontend projection. No Coroutine/Event creation or callbacks.
$expected = ['event_num', 'signal_listener_num', 'aio_task_num', 'aio_worker_num',
    'aio_queue_size', 'c_stack_size', 'coroutine_num', 'coroutine_peak_num', 'coroutine_last_cid'];
$withRing = array_merge($expected, ['iouring_task_num', 'iouring_sq_usage_percent', 'iouring_waiting_task_num']);
$observations = [];
for ($i = 0; $i < 2; ++$i) {
    $fields = Swoole\Coroutine::stats();
    if (array_keys($fields) !== $expected && array_keys($fields) !== $withRing) {
        throw new RuntimeException('Unexpected statistics field order');
    }
    foreach ($fields as $value) {
        if (!is_int($value)) {
            throw new RuntimeException('Statistics value must be a Zend integer');
        }
    }
    $observations[] = $fields;
}
echo json_encode($observations, JSON_THROW_ON_ERROR), "\n";
