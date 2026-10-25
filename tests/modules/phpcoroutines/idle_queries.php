<?php
// Ordinary idle getters and scheduler admission only. No Coroutine/Event creation,
// callbacks, IO, invalid context, warning, shutdown/failure or lifetime probe.
$observations = [];
for ($i = 0; $i < 2; ++$i) {
    $values = [
        'cid' => Swoole\Coroutine::getCid(),
        'parent' => Swoole\Coroutine::getPcid(),
        'main_parent' => Swoole\Coroutine::getPcid(-1),
        'elapsed' => Swoole\Coroutine::getElapsed(),
        'stack' => Swoole\Coroutine::getStackUsage(),
        'enable_scheduler' => Swoole\Coroutine::enableScheduler(),
        'disable_scheduler' => Swoole\Coroutine::disableScheduler(),
    ];
    if ($values['cid'] !== -1 || $values['parent'] !== false || $values['main_parent'] !== false
        || $values['elapsed'] !== -1 || $values['enable_scheduler'] !== false
        || $values['disable_scheduler'] !== false || !is_int($values['stack']) || $values['stack'] < 0) {
        throw new RuntimeException('Unexpected idle context query result');
    }
    $observations[] = $values;
}
echo json_encode($observations, JSON_THROW_ON_ERROR), "\n";
