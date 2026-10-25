<?php
// Real socketpair consumers of type_size, radix and decimal formatting.
// No listener, process, external service, upstream bootstrap or performance measurement.
if (!extension_loaded('swoole') || !function_exists('swoole_coroutine_socketpair')
    || !function_exists('Swoole\\Coroutine\\run') || !class_exists('Swoole\\Http\\Response')
    || !defined('AF_UNIX') || !defined('SOCK_STREAM')) {
    fwrite(STDERR, "UNAVAILABLE: Swoole coroutine/socket/HTTP API and POSIX socket constants required\n");
    exit(77);
}
function require_same($actual, $expected, string $label): void {
    if ($actual !== $expected) {
        throw new RuntimeException($label . ': actual=' . var_export($actual, true)
            . ' expected=' . var_export($expected, true));
    }
}
function pair_for_m19(): array {
    $pair = swoole_coroutine_socketpair(AF_UNIX, SOCK_STREAM, 0);
    if (!is_array($pair) || count($pair) !== 2) {
        throw new RuntimeException('socketpair unavailable');
    }
    return $pair;
}
function collect_wire($socket, string $expectedBody): string {
    $result = '';
    // Bound reads; a false/timeout is failure, not an empty successful result.
    for ($n = 0; $n < 8; $n++) {
        $data = $socket->recv(65536, 1);
        if ($data === false) {
            throw new RuntimeException('wire receive failed');
        }
        if ($data === '') {
            throw new RuntimeException('wire ended before complete HTTP message');
        }
        $result .= $data;
        $boundary = strpos($result, "\r\n\r\n");
        if ($boundary !== false && strlen($result) - $boundary - 4 >= strlen($expectedBody)) {
            return $result;
        }
    }
    throw new RuntimeException('wire did not contain complete HTTP message within bounded reads');
}
$completed = false;
Swoole\Coroutine\run(function () use (&$completed): void {
    // Socket::setProtocol calls swoole_type_size immediately; recvPacket checks
    // that configured width participates in actual framing, beyond set() success.
    foreach (['c', 'C', 's', 'S', 'n', 'v', 'l', 'L', 'N', 'V', 'q', 'Q', 'J', 'P'] as $format) {
        [$writer, $reader] = pair_for_m19();
        try {
            $header = pack($format, 3);
            $packet = $header . 'XYZ';
            require_same($reader->setProtocol([
                'open_length_check' => true,
                'package_length_type' => $format,
                'package_length_offset' => 0,
                'package_body_offset' => strlen($header),
                'package_max_length' => 64,
            ]), true, 'setProtocol ' . $format);
            require_same($writer->sendAll($packet, 1), strlen($packet), 'send ' . $format);
            require_same($reader->recvPacket(1), $packet, 'framed packet ' . $format);
        } finally {
            $writer->close();
            $reader->close();
        }
    }
    // HTTP/1 auto Content-Length calls swoole_itoa directly. Explicit reason also
    // reaches String::append(int), except when the buffer overlay replaces it.
    [$writer, $reader] = pair_for_m19();
    try {
        $response = Swoole\Http\Response::create($writer);
        if (!$response) { throw new RuntimeException('Response::create failed'); }
        require_same($response->status(201, 'M19'), true, 'status');
        require_same($response->end(str_repeat('A', 17)), true, 'end');
        $writer->close();
        $wire = collect_wire($reader, str_repeat('A', 17));
        [$headers, $body] = explode("\r\n\r\n", $wire, 2);
        require_same(str_starts_with($headers, "HTTP/1.1 201 M19\r\n"), true, 'status wire');
        require_same(preg_match('/(?:^|\r\n)Content-Length: 17(?:\r\n|$)/i', $headers), 1, 'length wire');
        require_same($body, str_repeat('A', 17), 'body');
    } finally {
        if (!$writer->isClosed()) { $writer->close(); }
        $reader->close();
    }
    // Nonempty HTTP/1 write calls swoole_dec2hex(length,16); validate lowercase
    // multi-digit chunk sizes against exact wire, not only decoded body equality.
    [$writer, $reader] = pair_for_m19();
    try {
        $response = Swoole\Http\Response::create($writer);
        if (!$response) { throw new RuntimeException('Response::create failed'); }
        require_same($response->write(str_repeat('A', 17)), true, 'write17');
        require_same($response->write(str_repeat('B', 31)), true, 'write31');
        require_same($response->end(), true, 'chunk end');
        $writer->close();
        $expected = "11\r\n" . str_repeat('A', 17) . "\r\n1f\r\n"
            . str_repeat('B', 31) . "\r\n0\r\n\r\n";
        [$headers, $body] = explode("\r\n\r\n", collect_wire($reader, $expected), 2);
        require_same(preg_match('/(?:^|\r\n)Transfer-Encoding: chunked(?:\r\n|$)/i', $headers), 1, 'chunk header');
        require_same($body, $expected, 'chunk wire');
    } finally {
        if (!$writer->isClosed()) { $writer->close(); }
        $reader->close();
    }
    $completed = true;
});
require_same($completed, true, 'consumer completion');
echo "M19 PHP consumers OK\n";
