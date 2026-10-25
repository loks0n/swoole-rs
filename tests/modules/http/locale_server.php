<?php
// Private actual-caller fixture; no fixed ports/files or locale changes in host.
$locale = getenv('HTTP_LOCALE');
if (setlocale(LC_CTYPE, $locale) === false) {
    fwrite(STDERR, "Requested locale unavailable\n");
    exit(77);
}
$root = getenv('TEST_DATA');
mkdir($root . "/\xc3\x80");
mkdir($root . '/I');
file_put_contents($root . "/\xc3\x80/data.txt", 'static-high');
file_put_contents($root . '/I/data.txt', 'static-ascii');
$server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_BASE);
$server->set([
    'log_file' => '/dev/null',
    'worker_num' => 1,
    'enable_coroutine' => false,
    'enable_static_handler' => true,
    'http_compression' => false,
    'document_root' => $root,
    'static_handler_locations' => ["/\xe3\x80", '/i'],
]);
$server->on('workerStart', static function () use ($locale) {
    if (setlocale(LC_CTYPE, $locale) === false) {
        throw new RuntimeException('Worker locale unavailable');
    }
});
$server->on('request', static function ($request, $response) {
    $response->header('Content-Type', 'text/plain');
    $response->end('dynamic');
});
$server->start();
