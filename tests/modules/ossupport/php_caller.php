<?php
// SPDX-License-Identifier: Apache-2.0
use Swoole\Coroutine as Co;
use Swoole\Coroutine\System;
function require_true($value, $message) { if (!$value) { throw new RuntimeException($message); } }
$dir = $argv[1];
$payload = str_repeat(implode('', array_map('chr', range(0, 255))), 256);
Co::set(['aio_core_worker_num' => 2, 'aio_worker_num' => 8, 'aio_max_wait_time' => 0.0001, 'aio_max_idle_time' => 0.5]);
$rounds = [];
for ($round = 0; $round < 3; ++$round) {
    $done = [];
    Co\run(function () use ($dir, $payload, $round, &$done) {
        $channel = new Co\Channel(16);
        for ($i = 0; $i < 16; ++$i) {
            Co::create(function () use ($dir, $payload, $round, $i, $channel) {
                $path = "$dir/$round-$i";
                require_true(System::writeFile($path, $payload, LOCK_EX) === strlen($payload), 'write bytes');
                require_true(System::readFile($path, LOCK_EX) === $payload, 'binary read bytes');
                require_true(System::writeFile($path, "\0tail\n", FILE_APPEND | LOCK_EX) === 6, 'append bytes');
                require_true(System::readFile($path) === $payload . "\0tail\n", 'append order');
                unlink($path);
                $channel->push($i);
            });
        }
        for ($i = 0; $i < 16; ++$i) { $done[] = $channel->pop(); }
    });
    sort($done);
    require_true($done === range(0, 15), 'exactly once completion');
    $rounds[] = count($done);
}
$process = new Swoole\Process(function ($child) use ($dir, $payload) {
    Co\run(function () use ($dir, $payload) {
        $path = "$dir/fork-child";
        require_true(System::writeFile($path, $payload) === strlen($payload), 'child write');
        require_true(System::readFile($path) === $payload, 'child read');
        unlink($path);
    });
    $child->write('child-ok');
    $child->exit(0);
}, false, SOCK_STREAM);
require_true($process->start() > 0, 'fork after pool teardown');
require_true($process->read() === 'child-ok', 'child callback delivery');
$status = Swoole\Process::wait(true);
require_true($status['code'] === 0 && $status['signal'] === 0, 'child clean exit');
echo json_encode(['rounds' => $rounds, 'binary_sha256' => hash('sha256', $payload), 'fork' => 'child-ok']), "\n";
