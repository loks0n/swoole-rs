<?php
$result = swr_reactor_blocking_supported();
if (count($result['outcomes']) !== 54 || $result['cases'] !== 7 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Ordinary blocking Socket/IOVector assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
