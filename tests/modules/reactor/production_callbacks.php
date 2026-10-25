<?php
$result = swr_reactor_callbacks_supported();
if (count($result['outcomes']) !== 22 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Supported production callback-storage assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
