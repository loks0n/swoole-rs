<?php
$result = swr_reactor_datagram_supported();
if (count($result['outcomes']) !== 72 || $result['cases'] !== 12 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Ordinary datagram assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
