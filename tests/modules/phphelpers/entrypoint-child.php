<?php
// Each parent owns/reaps one pipe_type0 child; named fatal stays native.
function check(bool $ok, string $message): void { if (!$ok) throw new RuntimeException($message); }
$coroutine = $argv[1] === 'coroutine';
$outcome = $argv[2];
function m26_named_child_target(bool $exception, bool $coroutine): void {
    echo "M26 named enter\n";
    check(m26_named_call('strlen', 'child') === 5, 'nested child entry');
    if ($coroutine) Swoole\Coroutine::sleep(0.001);
    if ($exception) throw new RuntimeException('M26 ordinary named exception');
    echo "M26 named return\n";
}
$process = new Swoole\Process(function () use ($coroutine, $outcome): void {
    if ($outcome === 'missing') m26_named_call('M26_named_missing_callback');
    else m26_named_call('m26_named_child_target', $outcome === 'exception', $coroutine);
}, false, 0, $coroutine);
$pid = $process->start();
check(is_int($pid) && $pid > 0, 'own named child started');
$status = Swoole\Process::wait(true);
check(is_array($status) && $status['pid'] === $pid, 'own named child reaped');
check($status['code'] === ($outcome === 'return' ? 0 : 255) && $status['signal'] === 0, 'exact native named child status');
echo json_encode(['coroutine' => $coroutine, 'outcome' => $outcome, 'code' => $status['code'], 'signal' => $status['signal']], JSON_THROW_ON_ERROR), "\n";
