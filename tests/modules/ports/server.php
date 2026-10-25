<?php
// Independent real ephemeral TCP lifecycle. Original PHPTs remain separate.
stream_set_write_buffer(STDOUT, 0);
$server = new Swoole\Server('127.0.0.1', 0, SWOOLE_BASE);
$server->set(['worker_num'=>1, 'log_level'=>SWOOLE_LOG_ERROR]);
$port = $server->ports[0];
$protocol = $argv[1] ?? 'length';
[$options, $expected] = match ($protocol) {
    'length' => [['open_length_check'=>true, 'package_length_type'=>'N',
                  'package_length_offset'=>0, 'package_body_offset'=>4,
                  'package_max_length'=>1024], pack('N', 13).'ports-runtime'],
    'eof' => [['open_eof_check'=>true, 'package_eof'=>"\r\n"], "ports-runtime\r\n"],
    'mqtt' => [['open_mqtt_protocol'=>true], "\x30\x03\x00\x01a"],
};
$port->set(['backlog'=>17, 'socket_buffer_size'=>65536,
            'kernel_socket_recv_buffer_size'=>8192, 'kernel_socket_send_buffer_size'=>8192,
            'open_tcp_keepalive'=>true, 'tcp_keepidle'=>1,
            'tcp_keepinterval'=>1, 'tcp_keepcount'=>3, ...$options]);
$server->on('WorkerStart', static function ($server) {
    echo 'READY ', json_encode(['port'=>$server->ports[0]->port]), "\n";
    fflush(STDOUT);
});
$port->on('Receive', static function ($server, $fd, $reactor, $data) use ($expected) {
    if ($data !== $expected) {
        throw new RuntimeException('unexpected framed payload');
    }
    if (!$server->send($fd, $data)) {
        throw new RuntimeException('send failed');
    }
    echo "OBSERVED framed-receive send shutdown\n";
    fflush(STDOUT);
    $server->shutdown();
});
if (!$server->start()) {
    throw new RuntimeException('server start failed');
}
