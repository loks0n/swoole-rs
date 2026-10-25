<?php
$case = getenv('HTTPBINDINGS_FATAL_CASE');
$settings = ['log_file' => '/dev/null'];
if (str_starts_with($case, 'types-')) {
    $settings['http_compression_types'] = match ($case) {
        'types-false' => false, 'types-string' => 'application/json', 'types-number' => 17,
    };
    $settings['compression_types'] = ['application/json'];
} else {
    file_put_contents(getenv('TEST_DATA') . '/file', 'blocked');
    $settings['upload_tmp_dir'] = new class($case) {
        public function __construct(private string $case) {}
        public function __toString(): string {
            echo "upload-convert\n";
            $request = Swoole\Http\Request::create();
            $request->parse("GET /nested-error HTTP/1.1\r\nHost: localhost\r\n\r\n");
            echo $request->server['request_uri'] . "\n";
            if ($this->case === 'throw-upload') throw new RuntimeException('conversion rejected');
            return getenv('TEST_DATA') . '/file/child';
        }
        public function __destruct() { echo "upload-destroyed\n"; }
    };
}
try {
    Swoole\Coroutine\run(function () use ($settings) {
        $server = new Swoole\Coroutine\Http\Server('127.0.0.1', 0, false);
        $server->set($settings);
        $server->handle('/', static function ($request, $response) { $response->end('unexpected'); });
        echo "settings-start\n";
        $server->start();
        echo "start-returned\n";
    });
    echo "run-returned\n";
} catch (Throwable $error) {
    echo 'caught:' . get_class($error) . ':' . $error->getMessage() . "\n";
}
