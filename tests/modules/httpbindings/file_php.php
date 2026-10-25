<?php
$mode = getenv('HTTPBINDINGS_MODE');
$root = getenv('TEST_DATA');
$payload = '';
for ($i = 0; $i < 32768; $i++) $payload .= chr($i % 256);
file_put_contents($root . '/payload.txt', $payload);
file_put_contents($root . '/empty.txt', '');
symlink($root . '/payload.txt', $root . '/copy.txt');
mkdir($root . '/directory');
$consume = static function ($request, $response) use ($root) {
    $case = json_decode($request->getContent(), true, flags: JSON_THROW_ON_ERROR);
    $name = match ($case['kind']) {
        'file' => $root . '/payload.txt', 'link' => $root . '/copy.txt',
        'empty' => $root . '/empty.txt', 'missing' => $root . '/missing.txt',
        'directory' => $root . '/directory', 'empty-name' => '',
    };
    $warnings = [];
    set_error_handler(static function ($level, $message) use (&$warnings, $root) {
        $warnings[] = str_replace($root, '<TEST_DATA>', $message);
        return true;
    });
    try {
        $response->status(201);
        if ($case['header'] === 1) $response->header('Content-Type', 'application/custom');
        if ($case['header'] === 2) $response->header('content-type', 'application/custom', false);
        if ($case['chunk']) $response->write('prefix');
        $result = $response->sendfile($name, $case['offset'], $case['length']);
        $writable = $response->isWritable();
        if (!$result && $writable) $response->end('failure');
        file_put_contents(getenv('HTTPBINDINGS_AUDIT') . '/' . $case['id'] . '.tmp',
            json_encode(['result' => $result, 'warnings' => $warnings,
                         'writable_after_sendfile' => $writable, 'last_error' => swoole_last_error()], JSON_THROW_ON_ERROR));
        rename(getenv('HTTPBINDINGS_AUDIT') . '/' . $case['id'] . '.tmp',
               getenv('HTTPBINDINGS_AUDIT') . '/' . $case['id'] . '.json');
    } finally {
        restore_error_handler();
    }
};
$settings = ['http_compression' => true, 'http_compression_min_length' => 0, 'log_file' => '/dev/null'];
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
