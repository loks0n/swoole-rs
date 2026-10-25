<?php
// Actual Process::start -> core fork, child Zend heap/cycle use and guards.
// Own anonymous pipes/children only. No listener, fixed path or external service.
function fork_require(bool $value, string $message): void {
    if (!$value) throw new RuntimeException($message);
}
$mode = $argv[1] ?? 'normal';
if ($mode === 'coroutine') {
    Swoole\Coroutine\run(function (): void {
        $process = new Swoole\Process(static function (): void {});
        $process->start(); // Native PHP fatal handler prints and exits255.
    });
    throw new RuntimeException('coroutine guard did not terminate');
}
if ($mode === 'async') {
    fork_require(swoole_async_set(['enable_coroutine' => false]), 'plain event callbacks configured before reactor');
    $process = new Swoole\Process(static function (): void {}); // Before the async pool exists.
    $contents = file_get_contents(__FILE__);
    Swoole\Coroutine\run(function () use ($contents, $process): void {
        fork_require(Swoole\Coroutine\System::readFile(__FILE__) === $contents, 'real async file read');
        Swoole\Event::defer(function () use ($process): void {
            fork_require(Swoole\Coroutine::getCid() < 0, 'async guard observed outside coroutine');
            $process->start(); // Must reject the still-live native async pool.
        });
    });
    throw new RuntimeException('async guard did not terminate');
}
fork_require($mode === 'normal', 'unknown fixture mode');
// A callback owns the only reference to this object. Timer cleanup must
// release that reference independently in the child and in the parent.
class ForkTimerCapture {
    public static int $released = 0;
    public function __destruct() { ++self::$released; }
}
$parent = getmypid();
$inherited = str_repeat("parent\0heap", 4096);
$expectedInherited = hash('sha256', $inherited);
foreach ([false, true] as $coroutine) {
    ForkTimerCapture::$released = 0;
    $capture = new ForkTimerCapture();
    $timer = Swoole\Timer::after(60000, static function () use ($capture): void {
        throw new RuntimeException('inherited timer unexpectedly fired');
    });
    unset($capture);
    fork_require(is_int($timer) && Swoole\Timer::exists($timer), 'parent live timer');
    fork_require(ForkTimerCapture::$released === 0, 'parent capture retained');
    $process = new Swoole\Process(function (Swoole\Process $child) use ($inherited, $expectedInherited, $coroutine, $timer): void {
        fork_require(!Swoole\Timer::exists($timer), 'child inherited timer removed');
        fork_require(ForkTimerCapture::$released === 1, 'child timer capture released before callback');
        fork_require(hash('sha256', $inherited) === $expectedInherited, 'inherited heap');
        $copy = $inherited;
        $copy[0] = 'X';
        $allocations = [];
        for ($n = 0; $n < 256; ++$n) $allocations[] = str_repeat((string) ($n % 10), 257 + $n);
        $cycle = new stdClass(); $cycle->self = $cycle;
        unset($cycle);
        fork_require(gc_collect_cycles() >= 1, 'child cyclic GC');
        fork_require((Swoole\Coroutine::getCid() > 0) === $coroutine, 'child coroutine setting');
        $message = json_encode(['inherited' => $expectedInherited, 'copy' => hash('sha256', $copy),
            'allocations' => count($allocations), 'coroutine' => $coroutine], JSON_THROW_ON_ERROR);
        fork_require($child->write($message) === strlen($message), 'child pipe write');
        // Return through native Process request shutdown and child cleanup.
    }, false, SOCK_DGRAM, $coroutine);
    $pid = $process->start();
    fork_require(is_int($pid) && $pid > 0 && getmypid() === $parent, 'parent fork result');
    $message = $process->read(8192);
    fork_require(is_string($message) && $message !== '', 'parent pipe read');
    $result = json_decode($message, true, 512, JSON_THROW_ON_ERROR);
    $copy = $inherited; $copy[0] = 'X';
    fork_require($result === ['inherited' => $expectedInherited, 'copy' => hash('sha256', $copy),
        'allocations' => 256, 'coroutine' => $coroutine], 'child payload');
    $waited = Swoole\Process::wait(true);
    fork_require($waited['pid'] === $pid && $waited['code'] === 0 && $waited['signal'] === 0, 'child reaped');
    fork_require(hash('sha256', $inherited) === $expectedInherited && getmypid() === $parent, 'parent heap intact');
    fork_require(Swoole\Timer::exists($timer), 'parent timer survives child cleanup');
    fork_require(ForkTimerCapture::$released === 0, 'parent capture survives child cleanup');
    fork_require(Swoole\Timer::clear($timer), 'parent timer cleared');
    fork_require(ForkTimerCapture::$released === 1, 'parent capture released exactly once');
    fork_require(!Swoole\Timer::exists($timer), 'parent timer absent after clear');
    $process->close();
}
Swoole\Event::wait(); // Drain the now-empty parent reactor before request shutdown.
echo "M19 PHP fork consumers OK\n";
