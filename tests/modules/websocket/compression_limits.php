<?php
declare(strict_types=1);

use Swoole\WebSocket\Frame;

// Each deliberate fatal runs in its own process. Mark setup separately so a
// filler allocation failure cannot masquerade as a WebSocket bailout.
$mode = $argv[1];
if ($mode === 'inflate') {
    $raw = gzdeflate(str_repeat('a', 32 * 1024 * 1024));
    $wire = "\xc2\x7e" . pack('n', strlen($raw)) . $raw;
    unset($raw);
    gc_mem_caches();
    ini_set('memory_limit', '8M');
    echo "BEGIN_INFLATE\n";
    Frame::unpack($wire);
} else {
    ini_set('memory_limit', '8M');
    $filler = [];
    $count = $mode === 'deflate-success' ? 280 : 295;
    for ($i = 0; $i < $count; ++$i) $filler[] = str_repeat('x', 16384);
    echo "BEGIN_DEFLATE\n";
    $packed = Frame::pack('abcdef', WEBSOCKET_OPCODE_BINARY,
        SWOOLE_WEBSOCKET_FLAG_FIN | SWOOLE_WEBSOCKET_FLAG_COMPRESS);
    $frame = Frame::unpack($packed);
    if (!$frame instanceof Frame || $frame->data !== 'abcdef') {
        throw new RuntimeException('Compressed roundtrip differs');
    }
}
echo "RETURNED\n";
