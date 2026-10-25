<?php
// Private fixture for actual HTTP/static caller checks and separately leased timing.
$directory = getenv('TEST_DATA');
foreach (['assets', 'assets/index', 'assets/list'] as $path) {
    mkdir("$directory/$path");
}
$payload = implode('', array_map('chr', range(0, 255)));
file_put_contents("$directory/assets/data.txt", str_repeat($payload, 16));
file_put_contents("$directory/assets/index/index.html", 'index fixture');
file_put_contents("$directory/assets/list/alpha.txt", 'alpha');
file_put_contents("$directory/assets/list/beta.txt", 'beta');
// Stable filesystem dates let the witness compare every header except Date.
foreach (['assets/data.txt', 'assets/index/index.html', 'assets/list/alpha.txt',
          'assets/list/beta.txt', 'assets/index', 'assets/list', 'assets'] as $path) {
    touch("$directory/$path", 1577836800);
}
$server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_BASE);
$server->set([
    'log_file' => '/dev/null',
    'worker_num' => 1,
    'enable_coroutine' => false,
    'enable_static_handler' => true,
    'http_compression' => false,
    'package_max_length' => 32 * 1024,
    'upload_max_filesize' => 128 * 1024,
    'document_root' => $directory,
    'static_handler_locations' => ['/assets'],
    'http_index_files' => ['index.html'],
    'http_autoindex' => true,
    'url_rewrite_rules' => ['/download/' => '/assets/'],
]);
$server->on('request', static function ($request, $response) {
    if ($request->server['request_uri'] === '/upload') {
        $files = [];
        foreach ($request->files ?? [] as $field => $file) {
            $files[$field] = [
                'name' => $file['name'], 'type' => $file['type'],
                'size' => $file['size'], 'error' => $file['error'],
                'sha256' => hash_file('sha256', $file['tmp_name']),
            ];
        }
        $response->header('Content-Type', 'application/json');
        $response->end(json_encode(['post' => $request->post, 'files' => $files]));
        return;
    }
    $response->header('Content-Type', 'text/plain');
    $response->end('dynamic fixture');
});
$server->start();
