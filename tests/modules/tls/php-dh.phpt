--TEST--
M21 owned actual PHP DH setting, native TLS1.2 DHE peer and teardown
--SKIPIF--
<?php
require __DIR__ . '/../../include/skipif.inc';
if (!extension_loaded('openssl') || !defined('STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT') || !defined('SWOOLE_SSL_TLSv1_2')) {
    die('skip requires supported native OpenSSL/TLS1.2 PHP configuration');
}
?>
--FILE--
<?php
require __DIR__ . '/../../include/bootstrap.php';
$pm = new SwooleTest\ProcessManager;
$pm->parentFunc = function ($pid) use ($pm) {
    // The pinned DH fixture is 1024 bits. Security level0 is test-local to force
    // its actual DHE consumer, not a production/default or trust-policy change.
    $context = stream_context_create(['ssl' => [
        'crypto_method' => STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT,
        'ciphers' => 'DHE-RSA-AES128-GCM-SHA256:@SECLEVEL=0',
        'verify_peer' => false,
        'verify_peer_name' => false,
    ]]);
    $client = stream_socket_client('tls://127.0.0.1:' . $pm->getFreePort(), $errno, $error, 5, STREAM_CLIENT_CONNECT, $context);
    Assert::resource($client);
    stream_set_timeout($client, 5);
    $crypto = stream_get_meta_data($client)['crypto'];
    Assert::same($crypto['protocol'], 'TLSv1.2');
    Assert::same($crypto['cipher_name'], 'DHE-RSA-AES128-GCM-SHA256');
    $message = "M21 explicit DH consumer\n";
    for ($offset = 0; $offset < strlen($message);) {
        $count = fwrite($client, substr($message, $offset));
        Assert::greaterThan($count, 0);$offset += $count;
    }
    Assert::same(fgets($client), $message);
    Assert::true(fclose($client));
    $pm->kill();
    echo "TLSv1.2 DHE-RSA-AES128-GCM-SHA256\n";
};
$pm->childFunc = function () use ($pm) {
    $server = new Swoole\Server('127.0.0.1', $pm->getFreePort(), SWOOLE_BASE, SWOOLE_SOCK_TCP | SWOOLE_SSL);
    Assert::true($server->set([
        'worker_num' => 1,
        'log_file' => '/dev/null',
        'ssl_cert_file' => SSL_FILE_DIR . '/server.crt',
        'ssl_key_file' => SSL_FILE_DIR . '/server.key',
        'ssl_protocols' => SWOOLE_SSL_TLSv1_2,
        'ssl_dhparam' => SSL_FILE_DIR . '/dhparams.pem',
        'ssl_ciphers' => 'DHE-RSA-AES128-GCM-SHA256:@SECLEVEL=0',
    ]));
    $server->on('workerStart', function () use ($pm) { $pm->wakeup(); });
    $buffers = [];
    $server->on('receive', function ($server, $fd, $reactor, $data) use (&$buffers) {
        $buffers[$fd] = ($buffers[$fd] ?? '') . $data;
        if (strpos($buffers[$fd], "\n") !== false) {
            Assert::same($buffers[$fd], "M21 explicit DH consumer\n");
            Assert::true($server->send($fd, $buffers[$fd]));unset($buffers[$fd]);
        }
    });
    $server->start();
};
$pm->childFirst();$pm->run();
echo "DONE\n";
?>
--EXPECT--
TLSv1.2 DHE-RSA-AES128-GCM-SHA256
DONE
