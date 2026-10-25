<?php
// Real coroutine startup consumer; all filesystem effects stay in TEST_DATA.
$settings = json_decode(getenv('HTTPBINDINGS_SETTINGS'), true, flags: JSON_THROW_ON_ERROR);
$events = [];
if (array_key_exists('upload_tmp_dir', $settings)) {
    $settings['upload_tmp_dir'] = new class($events) {
        private $events;
        public function __construct(&$events) { $this->events = &$events; }
        public function __toString(): string {
            $this->events[] = 'upload-string';
            $request = Swoole\Http\Request::create();
            $request->parse("GET /nested HTTP/1.1\r\nHost: localhost\r\n\r\n");
            $this->events[] = $request->server['request_uri'];
            return getenv('TEST_DATA') . '/nested/upload';
        }
    };
}
$settings += ['log_file' => '/dev/null'];
Swoole\Coroutine\run(function () use ($settings, &$events) {
    $server = new Swoole\Coroutine\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), false);
    $server->set($settings);
    $server->handle('/', static function ($request, $response) use (&$events) {
        $files = [];
        foreach (($request->files ?? []) as $key => $file) {
            $files[$key] = ['name' => $file['name'], 'type' => $file['type'],
                'size' => $file['size'], 'error' => $file['error'],
                'hash' => is_file($file['tmp_name']) ? hash_file('sha256', $file['tmp_name']) : null];
        }
        $response->header('Content-Type', 'application/json');
        $response->end(json_encode(['cookie' => $request->cookie ?? [],
            'post' => $request->post ?? [], 'files' => $files, 'events' => $events,
            'content' => bin2hex($request->getContent()), 'padding' => str_repeat('abcdefgh', 128)],
            JSON_THROW_ON_ERROR));
    });
    $server->handle('/stop', static function ($request, $response) use ($server) {
        $response->end('stopped');
        $server->shutdown();
    });
    $server->start();
});
