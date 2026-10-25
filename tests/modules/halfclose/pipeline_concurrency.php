<?php
$events = [];
$channel = new Swoole\Coroutine\Channel(1);
$persist = static function () use (&$events): void {
    $path = getenv('TEST_EVENTS');
    file_put_contents($path . '.tmp', json_encode((object) $events));
    rename($path . '.tmp', $path);
};
$server = new Swoole\Http\Server('127.0.0.1', (int) getenv('TEST_PORT'), SWOOLE_PROCESS);
$server->set(['worker_num' => 1, 'reactor_num' => 1, 'enable_coroutine' => true,
    'http_compression' => false, 'max_wait_time' => 1]);
$server->on('request', static function ($request, $response) use ($channel, &$events, $persist): void {
    if ($request->server['request_uri'] === '/first') {
        $events['first_started'] = true;
        $value = $channel->pop(2);
        $events['first_saw_second'] = $value === 'second';
        $events['first_accepted'] = $response->end($value === 'second' ? 'first:ok' : 'first:timeout');
        $events['first_finished'] = true;
    } elseif ($request->server['request_uri'] === '/second') {
        $events['second_before_first_finished'] = !($events['first_finished'] ?? false);
        $events['second_saw_first'] = $events['first_started'] ?? false;
        $channel->push('second');
        Swoole\Coroutine::sleep(.01);
        $events['second_accepted'] = $response->end('second:ok');
        $events['second_finished'] = true;
    } else {
        $response->end('ready');
        return;
    }
    $persist();
});
$server->start();
