<?php
$mode = getenv('HTTPBINDINGS_MODE');
$consume = static function ($request, $response) {
    $body = $request->getContent();
    $path = $request->server['request_uri'];
    $response->status(201);
    $response->header('Content-Type', 'application/octet-stream');
    $response->header('X-Mode', $path);
    $warnings = [];
    set_error_handler(static function ($level, $message) use (&$warnings) {
        $warnings[] = $message;
        return true;
    });
    try {
        if ($path === '/end') {
            $response->end($body);
            return;
        }
        if ($path === '/trailers') {
            $response->trailer('X-Test', "space + tilde~");
            $response->trailer('X-Empty', '');
        }
        $results = [];
        if ($path === '/chunks') {
            foreach (str_split($body, 17) ?: [''] as $part) $results[] = $response->write($part);
        } elseif ($path === '/end-data') {
            $results[] = $response->write('prefix');
            $response->end($body);
            return;
        } else {
            $results[] = $response->write($body);
        }
        $response->end('|meta=' . json_encode(['results' => $results, 'warnings' => $warnings], JSON_THROW_ON_ERROR));
    } finally {
        restore_error_handler();
    }
};
$settings = ['http_compression' => false, 'log_file' => '/dev/null'];
if ($mode === 'coroutine') {
    Swoole\Coroutine\run(function () use ($consume, $settings) {
        $server = new Swoole\Coroutine\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), false);
        $server->set($settings);
        $server->handle('/', $consume);
        $server->handle('/stop', static function ($request, $response) use ($server) {
            $response->end('stopped');
            $server->shutdown();
        });
        $server->start();
    });
} else {
    $server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_BASE);
    $server->set($settings + ['worker_num' => 1, 'enable_coroutine' => $mode === 'normal-coroutine']);
    $server->on('request', $consume);
    $server->start();
}
