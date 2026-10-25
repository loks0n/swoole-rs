<?php
// Private-port normal/coroutine consumers; the driver owns process-group cleanup.
$mode = getenv('HTTPBINDINGS_MODE');
$settings = ['http_compression' => getenv('HTTPBINDINGS_COMPRESSION') === '1',
             'http_compression_min_length' => 0, 'log_file' => '/dev/null'];
$level = getenv('HTTPBINDINGS_COMPRESSION_LEVEL');
if ($level !== false) $settings['http_compression_level'] = (int) $level;
$consume = static function ($request, $response, string $route) {
    $content = $request->getContent();
    $response->status(207, 'Multi-Status');
    $response->header('x-miXed-KEY', 'native-response');
    $response->cookie('binding', "space + tilde~", 0, '/');
    $response->end(json_encode([
        'route' => $route,
        'uri' => $request->server['request_uri'],
        'method' => $request->server['request_method'],
        'query' => $request->get ?? [],
        'post' => $request->post ?? [],
        'cookie' => $request->cookie ?? [],
        'header' => $request->header,
        'content' => bin2hex($content),
        'rawContent' => bin2hex($request->rawContent()),
    ], JSON_THROW_ON_ERROR));
};
if ($mode === 'coroutine') {
    Swoole\Coroutine\run(function () use ($consume, $settings) {
        $server = new Swoole\Coroutine\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), false);
        $server->set($settings);
        foreach (['/', '/Alpha', '/post'] as $route) {
            $server->handle($route, static function ($request, $response) use ($consume, $route) {
                $consume($request, $response, $route);
            });
        }
        $server->handle('/stop', static function ($request, $response) use ($server) {
            $response->end('stopped');
            $server->shutdown();
        });
        $server->start();
    });
} else {
    $server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_BASE);
    $server->set($settings + ['worker_num' => 1, 'enable_coroutine' => $mode === 'normal-coroutine']);
    $server->on('request', static function ($request, $response) use ($consume) {
        $consume($request, $response, 'normal');
    });
    $server->start();
}
