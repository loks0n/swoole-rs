<?php
// Independent diagnostic. The pinned PHPT/assertions are never modified/run here.
require __DIR__ . '/tests/include/bootstrap.php';

use Swoole\Atomic;
use Swoole\Coroutine\Lock;
use Swoole\Coroutine\WaitGroup;
use Swoole\Http\Server;
use Swoole\Runtime;
use function Swoole\Coroutine\go;
use function Swoole\Coroutine\run;

$sequence = new Atomic();
$holders = new Atomic();
$violations = new Atomic();
$completed = new Atomic();
$mode = getenv('LOCK_ORDER_MODE');
if (!in_array($mode, ['parallel', 'two-first'], true)) {
    throw new RuntimeException('Unknown diagnostic mode');
}
function trace_lock_event(string $event, int $request, array $extra = []): void {
    global $sequence;
    $row = ['sequence' => $sequence->add(), 'pid' => getmypid(),
        'cid' => Swoole\Coroutine::getCid(), 'event' => $event, 'request' => $request] + $extra;
    fwrite(STDERR, 'LOCKTRACE ' . json_encode($row, JSON_THROW_ON_ERROR) . "\n");
}
$pm = new SwooleTest\ProcessManager();
$pm->parentFunc = function () use ($pm, $mode, $holders, $violations, $completed, $sequence) {
    Runtime::enableCoroutine(SWOOLE_HOOK_ALL);
    $received = [];
    run(function () use ($pm, $mode, &$received, $completed) {
        $batch = function (array $requests) use ($pm, &$received) {
            $wait = new WaitGroup();
            foreach ($requests as $value) {
                go(function () use ($pm, $wait, $value, &$received) {
                    $wait->add();
                    trace_lock_event('client_start', $value);
                    $wire = httpPost("http://127.0.0.1:{$pm->getFreePort()}?value=$value", []);
                    $data = json_decode($wire, true, 512, JSON_THROW_ON_ERROR);
                    $wanted = $value === 3 ? 'value 3' : 'lock' . $value;
                    if (($data['result'] ?? null) !== $wanted) throw new RuntimeException('Unexpected response');
                    trace_lock_event('client_received', $value);
                    $received[] = $value;
                    $wait->done();
                });
            }
            $wait->wait();
        };
        if ($mode === 'two-first') {
            $batch([2]);
            $batch([1, 3]);
        } else {
            $batch([1, 2, 3]);
        }
        // Drain actual handler completion, rather than assume unlock has finished
        // merely because the client received the already-sent response.
        for ($n = 0; $completed->get() !== 3 && $n < 5000; $n++) Swoole\Coroutine::sleep(0.001);
        if ($completed->get() !== 3) throw new RuntimeException('Handlers did not drain');
    });
    echo json_encode(['mode' => $mode, 'received' => $received,
        'holders_after' => $holders->get(), 'violations' => $violations->get(),
        'handlers_completed' => $completed->get(), 'event_count' => $sequence->get()], JSON_THROW_ON_ERROR), "\n";
    $pm->kill();
};
$pm->childFunc = function () use ($pm, $holders, $violations, $completed) {
    swoole_async_set(['log_file' => '/dev/null']);
    $lock = new Lock(true);
    if ($lock->lock() !== false || $lock->unlock() !== false ||
        $lock->errCode !== SWOOLE_ERROR_CO_OUT_OF_COROUTINE) throw new RuntimeException('Outside-coroutine boundary changed');
    $server = new Server('127.0.0.1', $pm->getFreePort());
    $server->set(['log_file' => '/dev/null', 'worker_num' => 4,
        'enable_coroutine' => true, 'hook_flags' => SWOOLE_HOOK_ALL]);
    $server->on('workerStart', function () use ($pm) { $pm->wakeup(); });
    $server->on('request', function ($request, $response) use ($lock, $holders, $violations, $completed) {
        $value = (int) $request->get['value'];
        trace_lock_event('server_enter', $value);
        $response->header('Content-Type', 'text/plain');
        if ($value === 1 || $value === 2) {
            trace_lock_event('before_lock', $value);
            if (!$lock->lock()) throw new RuntimeException('Lock acquisition failed');
            $active = $holders->add();
            if ($active !== 1) $violations->add();
            trace_lock_event('acquired', $value, ['active_holders' => $active]);
            if ($value === 1) sleep(1);
            trace_lock_event('before_response', $value);
            $response->end(json_encode(['result' => 'lock' . $value]) . PHP_EOL);
            trace_lock_event('response_returned', $value);
            $active = $holders->sub();
            trace_lock_event('before_unlock', $value, ['active_holders' => $active]);
            if (!$lock->unlock()) throw new RuntimeException('Lock release failed');
            trace_lock_event('unlocked', $value);
        } else {
            trace_lock_event('before_response', $value);
            $response->end(json_encode(['result' => 'value 3']) . PHP_EOL);
            trace_lock_event('response_returned', $value);
        }
        $completed->add();
    });
    $server->start();
};
$pm->childFirst();
$pm->run();
