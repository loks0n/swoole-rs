<?php
$directory = getenv('TEST_DATA');
$save = static function ($name, $value) use ($directory): void {
    $path = $directory . '/' . $name . '.json';
    file_put_contents($path . '.tmp', json_encode($value));
    rename($path . '.tmp', $path);
};
$server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_PROCESS);
$drain = getenv('TEST_DRAIN') === '1';
$exit = getenv('TEST_EXIT_ZERO') === '1' ? FFI::cdef('void _exit(int status);') : null;
$server->set(['worker_num' => 1, 'reactor_num' => 1, 'enable_coroutine' => true,
    'http_compression' => false, 'max_wait_time' => $drain ? 10 : 1]);
$server->on('workerStart', static function ($server, $id) use ($save): void {
    $save('ready', ['pid' => getmypid(), 'worker_id' => $id]);
});
$server->on('request', static function ($request, $response) use ($server, $save, $directory, $drain, $exit): void {
    if ($request->server['request_uri'] === '/hold') {
        $save('hold', ['pid' => getmypid(), 'session' => $request->fd, 'started' => true]);
        if ($drain) {
            $deadline = microtime(true) + 8;
            while (!file_exists($directory . '/release') && microtime(true) < $deadline) {
                Swoole\Coroutine::sleep(.01);
            }
        } else {
            Swoole\Coroutine::sleep((float) getenv('TEST_HOLD_SECONDS'));
        }
        $accepted = $response->end('complete');
        $save('finished', ['pid' => getmypid(), 'accepted' => $accepted]);
    } elseif ($request->server['request_uri'] === '/exit-zero' && $exit !== null) {
        $save('exit-zero', ['pid' => getmypid(), 'status' => 0, 'function' => 'libc _exit']);
        $exit->_exit(0);
        throw new RuntimeException('_exit returned');
    } elseif ($request->server['request_uri'] === '/stop') {
        $response->end('stopping');
        $save('stop', ['accepted' => $server->stop(0)]);
    } elseif ($request->server['request_uri'] === '/identity') {
        $response->end((string) getmypid());
    } else {
        $response->end('ready');
    }
});
$server->start();
