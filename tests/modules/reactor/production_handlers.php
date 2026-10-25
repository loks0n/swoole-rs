<?php
$result = swr_reactor_handlers_supported();
if ($result['cases'] !== 1462 || $result['native_invocations'] !== 190 || count($result['outcomes']) !== 2194 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Supported production handler-routing assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
