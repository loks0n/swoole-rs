<?php
$result = swr_reactor_ordinary_supported();
if (count($result['outcomes']) !== 180 || $result['cases'] !== 35 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Ordinary Socket assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
