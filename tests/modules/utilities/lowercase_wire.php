<?php
// New normal wire witness; the upstream trailer PHPT remains unchanged.
require getenv('M14_WIRE_SUPPORT') . '/tests/include/bootstrap.php';
function m14_wire_check(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}
$log = getenv('M14_WIRE_LOG');
$pm = new SwooleTest\ProcessManager;
$pm->parentFunc = function () use ($pm) {
    $connection = null;
    try {
        $connection = stream_socket_client('tcp://127.0.0.1:' . $pm->getFreePort(), $errno, $error, 5);
        m14_wire_check(is_resource($connection), 'connect');
        stream_set_timeout($connection, 5);
        $request = "GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
        while ($request !== '') {
            $written = fwrite($connection, $request);
            m14_wire_check($written !== false && $written > 0, 'request write');
            $request = substr($request, $written);
        }
        $wire = stream_get_contents($connection);
        $metadata = stream_get_meta_data($connection);
        m14_wire_check(!$metadata['timed_out'] && is_string($wire), 'response completes');
        $parts = explode("\r\n\r\n", $wire, 2);
        m14_wire_check(count($parts) === 2 && str_starts_with($parts[0], 'HTTP/1.1 200 '), 'HTTP response');
        m14_wire_check(stripos($parts[0], 'transfer-encoding: chunked') !== false, 'chunked response');
        $expected = "content-md5: " . md5('hello world') . "\r\nx-mixed-key: first\r\nx-42-key: second\r\ndup-key: last\r\n\r\n";
        $end = strpos($parts[1], "\r\n0\r\n");
        m14_wire_check($end !== false && substr($parts[1], $end + 5) === $expected, 'exact lowercase wire trailers');
        m14_wire_check(str_contains($parts[1], "\r\nhello world\r\n"), 'body retained');
        echo json_encode(['trailer_keys' => ['content-md5', 'x-mixed-key', 'x-42-key', 'dup-key'],
            'duplicate_last' => true, 'timed_out' => $metadata['timed_out'], 'wire_base64' => base64_encode($wire)], JSON_THROW_ON_ERROR), "\n";
    } finally {
        if (is_resource($connection)) { fclose($connection); }
        $pm->kill();
    }
};
$pm->childFunc = function () use ($pm, $log) {
    $server = new Swoole\Http\Server('127.0.0.1', $pm->getFreePort(), SWOOLE_PROCESS);
    $server->set(['worker_num' => 1, 'log_file' => $log]);
    $server->on('workerStart', function () use ($pm) { $pm->wakeup(); });
    $server->on('request', function ($request, $response) {
        m14_wire_check($response->header('Trailer', 'Content-MD5, X-MIXED-Key, X-42-KEY, DUP-KEY'), 'trailer declaration');
        m14_wire_check($response->write('hello world'), 'body write');
        foreach (['Content-MD5' => md5('hello world'), 'X-MIXED-Key' => 'first', 'X-42-KEY' => 'second',
                  'DUP-KEY' => 'old', 'Dup-Key' => 'last'] as $key => $value) {
            m14_wire_check($response->trailer($key, $value), 'trailer assignment');
        }
        m14_wire_check($response->end(), 'response end');
    });
    $server->start();
};
$pm->childFirst();
$pm->run();
