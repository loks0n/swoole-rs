<?php
error_reporting(E_ALL);
[$script, $case, $backend] = $argv;
if (PHP_OS_FAMILY === 'Darwin') {
    swoole_async_set(['enable_kqueue' => $backend === 'kqueue']);
}
function require_ok(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}
$pair = stream_socket_pair(STREAM_PF_UNIX, STREAM_SOCK_STREAM, STREAM_IPPROTO_IP);
require_ok(is_array($pair), 'socketpair');
foreach ($pair as $fd) { stream_set_blocking($fd, false); }
$trace = [];
$done = false;
$read = false;
$writesAfterRead = 0;
$ownerPid = getmypid();
register_shutdown_function(static function () use (&$trace, &$done, &$writesAfterRead, $ownerPid): void {
    if (getmypid() !== $ownerPid) { return; }
    echo 'RESULT ' . json_encode(['done' => $done, 'trace' => $trace, 'writes_after_read' => $writesAfterRead]) . "\n";
});
echo 'BEFORE ' . getmypid() . "\n";
flush();
require_ok(trim(fgets(STDIN)) === 'go', 'before handshake');
if ($case === 'remove') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace, &$read): void {
        require_ok(fread($fd, 16) === 'one', 'read payload');
        $read = true;
        $trace[] = 'read';
        require_ok(Swoole\Event::del($fd), 'remove readable');
    }, static function ($fd) use (&$read, &$writesAfterRead): void {
        if ($read) { ++$writesAfterRead; }
        require_ok(Swoole\Event::set($fd, null, null, SWOOLE_EVENT_READ), 'disable write');
    }, SWOOLE_EVENT_READ | SWOOLE_EVENT_WRITE) !== false, 'add');
    require_ok(fwrite($pair[1], 'one') === 3, 'write peer');
} elseif ($case === 'readd') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace, $pair): void {
        require_ok(fread($fd, 16) === 'one', 'first payload');
        $trace[] = 'first';
        require_ok(Swoole\Event::del($fd), 'remove old registration');
        require_ok(Swoole\Event::add($fd, static function ($fd) use (&$trace): void {
            require_ok(fread($fd, 16) === 'two', 'replacement payload');
            $trace[] = 'replacement';
            require_ok(Swoole\Event::del($fd), 'remove replacement');
        }) !== false, 'replacement add');
        require_ok(fwrite($pair[1], 'two') === 3, 'replacement write');
    }) !== false, 'first add');
    require_ok(fwrite($pair[1], 'one') === 3, 'first write');
} elseif ($case === 'roundtrip') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace): void {
        require_ok(fread($fd, 16) === 'one', 'request bytes');
        $trace[] = 'request';
        require_ok(Swoole\Event::write($fd, 'reply'), 'native Event::write');
    }) !== false, 'request add');
    require_ok(Swoole\Event::add($pair[1], static function ($fd) use (&$trace, $pair): void {
        require_ok(fread($fd, 16) === 'reply', 'response bytes');
        $trace[] = 'response';
        require_ok(Swoole\Event::del($pair[0]), 'request del');
        require_ok(Swoole\Event::del($fd), 'response del');
    }) !== false, 'response add');
    require_ok(fwrite($pair[1], 'one') === 3, 'request write');
} elseif ($case === 'queued') {
    $prefix = '';
    $chunk = str_repeat("prefill\0", 2048);
    do {
        $sent = fwrite($pair[0], $chunk);
        require_ok(is_int($sent) && $sent >= 0, 'prefill send');
        $prefix .= substr($chunk, 0, $sent);
        require_ok(strlen($prefix) < 32 * 1024 * 1024, 'bounded local socket capacity');
    } while ($sent > 0);
    require_ok($prefix !== '', 'socket reached backpressure');
    $first = str_repeat("first\0", 65536);
    $second = str_repeat("second\xff", 65536);
    $expectedLength = strlen($prefix) + strlen($first) + strlen($second);
    $expectedHash = hash('sha256', $prefix . $first . $second);
    $received = 0;
    $hash = hash_init('sha256');
    require_ok(Swoole\Event::add($pair[0], static function (): void {
        throw new RuntimeException('unexpected producer read');
    }) !== false, 'queued producer add');
    require_ok(Swoole\Event::add($pair[1], static function ($fd) use (&$trace, $pair, &$received, $hash, $expectedLength, $expectedHash): void {
        $bytes = fread($fd, 65536);
        require_ok(is_string($bytes) && $bytes !== '', 'queued response bytes');
        $received += strlen($bytes);
        hash_update($hash, $bytes);
        require_ok($received <= $expectedLength, 'no duplicate queued bytes');
        if ($received === $expectedLength) {
            require_ok(hash_final($hash) === $expectedHash, 'exact queued byte order');
            $trace[] = 'drained';
            require_ok(Swoole\Event::del($pair[0]), 'queued producer del');
            require_ok(Swoole\Event::del($fd), 'queued consumer del');
        }
    }) !== false, 'queued consumer add');
    require_ok(Swoole\Event::write($pair[0], $first), 'blocked Event::write');
    require_ok(Swoole\Event::write($pair[0], $second), 'already queued Event::write');
    $trace[] = 'queued';
} elseif ($case === 'suspend') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace): void {
        require_ok(fread($fd, 16) === 'one', 'suspended payload');
        require_ok(Swoole\Coroutine::getCid() > 0, 'native callback coroutine');
        $trace[] = 'before-yield';
        Swoole\Coroutine::sleep(0.001);
        $trace[] = 'after-yield';
        require_ok(Swoole\Event::del($fd), 'suspended callback del');
    }) !== false, 'suspended add');
    require_ok(fwrite($pair[1], 'one') === 3, 'suspended write');
} elseif ($case === 'fork') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace): void {
        require_ok(fread($fd, 16) === 'parent', 'parent after fork');
        $trace[] = 'parent';
        require_ok(Swoole\Event::del($fd), 'parent del');
    }) !== false, 'parent add');
} elseif ($case === 'fatal') {
    require_ok(Swoole\Event::add($pair[0], static function ($fd) use (&$trace): void {
        require_ok(fread($fd, 16) === 'one', 'fatal callback payload');
        $trace[] = 'read';
        trigger_error('m05 ordinary callback fatal', E_USER_ERROR);
    }) !== false, 'fatal add');
    require_ok(fwrite($pair[1], 'one') === 3, 'fatal write');
} else {
    throw new RuntimeException('unknown case');
}
echo 'READY ' . getmypid() . "\n";
flush();
require_ok(trim(fgets(STDIN)) === 'go', 'ready handshake');
if ($case === 'fork') {
    $child = new Swoole\Process(static function (Swoole\Process $process): void {
        $local = stream_socket_pair(STREAM_PF_UNIX, STREAM_SOCK_STREAM, STREAM_IPPROTO_IP);
        require_ok(is_array($local), 'child socketpair');
        $received = false;
        require_ok(Swoole\Event::add($local[0], static function ($fd) use (&$received): void {
            require_ok(fread($fd, 16) === 'child', 'child read');
            $received = true;
            require_ok(Swoole\Event::del($fd), 'child del');
        }) !== false, 'child add');
        require_ok(fwrite($local[1], 'child') === 5, 'child write');
        Swoole\Event::wait();
        require_ok($received, 'child callback');
        foreach ($local as $fd) { fclose($fd); }
        require_ok($process->write('child-complete') === 14, 'child report');
    });
    $pid = $child->start();
    require_ok(is_int($pid) && $pid > 0, 'fork');
    require_ok($child->read() === 'child-complete', 'parent child report');
    $status = Swoole\Process::wait(true);
    require_ok($status['pid'] === $pid && $status['code'] === 0 && $status['signal'] === 0, 'child status');
    $trace[] = 'child-complete';
    require_ok(fwrite($pair[1], 'parent') === 6, 'parent write');
}
Swoole\Event::wait();
require_ok($writesAfterRead === 0, 'removed callback fired again');
$expected = ['remove' => ['read'], 'readd' => ['first', 'replacement'], 'roundtrip' => ['request', 'response'], 'fork' => ['child-complete', 'parent'], 'suspend' => ['before-yield', 'after-yield'], 'queued' => ['queued', 'drained']];
require_ok($trace === ($expected[$case] ?? null), 'defined callback trace');
foreach ($pair as $fd) { fclose($fd); }
$done = true;
