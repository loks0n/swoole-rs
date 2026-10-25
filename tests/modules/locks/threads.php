<?php
// Valid native-thread ownership: each thread unlocks only its own acquisition.
function ensure_thread($value, string $message): void {
    if (!$value) { throw new RuntimeException($message); }
}
ensure_thread(PHP_ZTS && class_exists('Swoole\Thread\Barrier'), 'real ZTS/thread build required');
$arguments = Swoole\Thread::getArguments();
if ($arguments && $arguments[0] === 'normal-lock-worker') {
    [, $small, $large, $protected, $lock, $barrier] = $arguments;
    $barrier->wait();
    for ($i = 0; $i < 10000; $i++) { $small->add(); $large->add(); }
    for ($i = 0; $i < 1000; $i++) {
        ensure_thread($lock->lock(), 'worker lock');
        try { $protected->set($protected->get() + 1); }
        finally { ensure_thread($lock->unlock(), 'same worker unlock'); }
    }
    exit(0);
}
$small = new Swoole\Thread\Atomic();
$large = new Swoole\Thread\Atomic\Long();
$protected = new Swoole\Thread\Atomic();
$lock = new Swoole\Thread\Lock();
$barrier = new Swoole\Thread\Barrier(3);
$workers = [new Swoole\Thread(__FILE__, 'normal-lock-worker', $small, $large, $protected, $lock, $barrier),
            new Swoole\Thread(__FILE__, 'normal-lock-worker', $small, $large, $protected, $lock, $barrier)];
$barrier->wait();
foreach ($workers as $worker) {
    ensure_thread($worker->join() && $worker->getExitStatus() === 0, 'normal worker completion');
}
ensure_thread($small->get() === 20000 && $large->get() === 20000, 'concurrent atomic increments');
ensure_thread($protected->get() === 2000, 'mutex protected read/modify/write');
echo json_encode(['workers'=>2, 'atomic32'=>$small->get(), 'atomic64'=>$large->get(),
                  'mutex_protected'=>$protected->get(), 'barrier_participants'=>3,
                  'same_thread_unlock'=>true], JSON_THROW_ON_ERROR), "\n";
