<?php
// Normal initialized callback lookup only: no callback execution, reentry or lifetime hooks.
$server = new Swoole\Server('127.0.0.1', 0, SWOOLE_BASE);
$port = $server->ports[0];
$events = ['connect', 'receive', 'close', 'packet', 'request', 'handshake',
           'beforehandshakeresponse', 'open', 'message', 'disconnect', 'bufferfull', 'bufferempty'];
$callbacks = [];
foreach ($events as $event) {
    $callback = static function () {};
    if ($port->on($event, $callback) !== true) throw new RuntimeException('register '.$event);
    $callbacks[$event] = $callback;
}
$names = ['', 'unknown', "connect\0", "\xffreceive", 0, 42, true, false, null];
foreach ($events as $event) {
    $names[] = $event;
    $names[] = strtoupper($event);
    for ($byte = 0; $byte < 256; $byte++) $names[] = chr($byte).substr(strtoupper($event), 1);
}
$checks = 0;
$settings = [];
foreach (['C', '', 'tr_TR.UTF-8'] as $locale) {
    $active = setlocale(LC_CTYPE, $locale);
    if ($active === false) continue;
    $settings[] = $active;
    foreach ($names as $name) {
        $expected = $callbacks[strtolower((string) $name)] ?? null;
        if ($port->getCallback($name) !== $expected) throw new RuntimeException('getter check '.$checks);
        $checks++;
    }
}
echo json_encode(['getter_checks' => $checks, 'locales' => $settings, 'callbacks' => count($callbacks)]), "\n";
