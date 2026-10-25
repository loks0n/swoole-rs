<?php
// Defined single-owner primitives only. No threads/coroutines, IPC or fault profiles.
function owned_check(bool $result, string $message): void {
    if (!$result) throw new RuntimeException($message);
}
owned_check(PHP_INT_SIZE === 8 && !PHP_ZTS, 'this fixture requires 64-bit NTS');
$observations = ['atomic_checks' => [], 'owned_lock_roundtrips' => [], 'unavailable_lock_kinds' => []];
foreach (['Swoole\\Atomic', 'Swoole\\Atomic\\Long'] as $class) {
    $checks = 0;
    for ($i = 0; $i < 256; $i++) {
        $value = ($i * 7919) % 100000;
        if ($class === 'Swoole\\Atomic\\Long' && ($i & 1)) $value += 1 << 40;
        $atomic = new $class($value);
        owned_check($atomic->get() === $value, 'initial value');
        owned_check($atomic->add(7) === $value + 7, 'add');
        owned_check($atomic->sub(3) === $value + 4, 'subtract');
        owned_check($atomic->cmpset($value + 4, $value + 9) === true, 'matching compare/exchange');
        owned_check($atomic->cmpset($value + 4, 0) === false, 'nonmatching compare/exchange');
        owned_check($atomic->get() === $value + 9, 'failed comparison preserves value');
        $atomic->set($value + 1);
        owned_check($atomic->get() === $value + 1, 'set');
        $checks += 7;
    }
    $observations['atomic_checks'][$class] = $checks;
}
foreach (['MUTEX', 'RWLOCK', 'SPINLOCK'] as $kind) {
    $constant = 'Swoole\\Lock::'.$kind;
    if (!defined($constant)) {
        $observations['unavailable_lock_kinds'][] = $kind;
        continue;
    }
    $lock = new Swoole\Lock(constant($constant));
    for ($i = 0; $i < 128; $i++) {
        owned_check($lock->lock() === true, 'uncontended acquisition '.$kind);
        owned_check($lock->unlock() === true, 'same owner release '.$kind);
    }
    $observations['owned_lock_roundtrips'][$kind] = 128;
}
owned_check(isset($observations['owned_lock_roundtrips']['MUTEX']), 'mutex must be available');
echo json_encode($observations, JSON_THROW_ON_ERROR), "\n";
