<?php
// Independent PHP boundary observations, compared verbatim per native/Rust pair.
if (PHP_ZTS && class_exists('Swoole\Thread')) {
    $arguments = Swoole\Thread::getArguments();
    if ($arguments && $arguments[0] === 'atomic-worker') {
        for ($i = 0; $i < 10000; $i++) {
            $arguments[1]->add();
            $arguments[2]->add();
        }
        exit(0);
    }
}
function atomic_values($class): array {
    $a = new $class(-1);
    $values = [$a->get(), $a->add(), $a->sub(), $a->cmpset(-1, 123), $a->get()];
    $a->set(PHP_INT_MAX);
    $values[] = $a->get();
    $values[] = $a->add();
    $values[] = $a->sub();
    $values[] = $a->cmpset(7, 8);
    $values[] = $a->get();
    return $values;
}
$observations = [];
foreach (['Swoole\Atomic', 'Swoole\Atomic\Long'] as $class) {
    $observations[$class] = atomic_values($class);
}
foreach (['MUTEX', 'RWLOCK', 'SPINLOCK'] as $kind) {
    if (!defined('Swoole\Lock::' . $kind)) {
        $observations['locks'][$kind] = 'unavailable';
        continue;
    }
    $lock = new Swoole\Lock(constant('Swoole\Lock::' . $kind));
    foreach ([0, -1, 0.005] as $timeout) {
        $observations['locks'][$kind][] = [$lock->lock(LOCK_EX | LOCK_NB, $timeout), $lock->unlock()];
    }
}
if (PHP_ZTS && class_exists('Swoole\Thread\Atomic')) {
    foreach (['Swoole\Thread\Atomic', 'Swoole\Thread\Atomic\Long'] as $class) {
        $observations[$class] = atomic_values($class);
    }
    $a = new Swoole\Thread\Atomic();
    $b = new Swoole\Thread\Atomic\Long();
    $workers = [new Swoole\Thread(__FILE__, 'atomic-worker', $a, $b), new Swoole\Thread(__FILE__, 'atomic-worker', $a, $b)];
    foreach ($workers as $worker) {
        if (!$worker->join() || $worker->getExitStatus() !== 0) {
            throw new RuntimeException('Atomic worker failed');
        }
    }
    if ($a->get() !== 20000 || $b->get() !== 20000) {
        throw new RuntimeException('Concurrent atomic increments lost');
    }
    $observations['thread_counts'] = [$a->get(), $b->get()];
}
$coLock = new Swoole\Coroutine\Lock();
$events = [];
Swoole\Coroutine\run(function () use ($coLock, &$events) {
    if (!$coLock->lock() || !$coLock->lock()) {
        throw new RuntimeException('Coroutine owner reentrancy failed');
    }
    $events[] = 'held';
    Swoole\Coroutine::create(function () use ($coLock, &$events) {
        if (!$coLock->lock()) {
            throw new RuntimeException('Contender failed to acquire');
        }
        $events[] = 'contender';
        if (!$coLock->unlock()) {
            throw new RuntimeException('Contender failed to release');
        }
    });
    Swoole\Coroutine::sleep(0.005);
    $events[] = 'release';
    if (!$coLock->unlock()) {
        throw new RuntimeException('Owner failed to release');
    }
});
if ($events !== ['held', 'release', 'contender']) {
    throw new RuntimeException('Coroutine mutual exclusion order failed');
}
$observations['coroutine_sequence'] = $events;
echo json_encode($observations, JSON_THROW_ON_ERROR), "\n";
