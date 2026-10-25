<?php
// Real String storage allocation through the existing plain WebSocket API.
$payload = str_repeat('x', 4 * 1024 * 1024);
$mode = $argv[1];
if ($mode === 'success') {
    $frame = Swoole\WebSocket\Server::pack($payload);
    $decoded = Swoole\WebSocket\Server::unpack($frame);
    if ($decoded->data !== $payload || strlen($frame) !== strlen($payload) + 10) {
        throw new RuntimeException('Packed bytes differ');
    }
    echo json_encode(['bytes' => strlen($payload), 'frame_sha256' => hash('sha256', $frame)]), "\n";
    exit;
}
if ($mode !== 'fatal') throw new RuntimeException('Unknown mode');
echo "SETUP ", hash('sha256', $payload), "\n";
register_shutdown_function(static function () {
    $error = error_get_last();
    echo "SHUTDOWN ", $error['type'] ?? 0, "\n";
});
$limit = memory_get_usage(true) + 1024 * 1024;
if (ini_set('memory_limit', (string) $limit) === false) throw new RuntimeException('Cannot set limit');
echo "LIMIT ", $limit, "\nOPERATION plain-pack\n";
$frame = Swoole\WebSocket\Server::pack($payload);
echo "RETURN ", strlen($frame), "\n";
