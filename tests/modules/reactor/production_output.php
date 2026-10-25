<?php
$result = swr_reactor_output_supported();
if (count($result['outcomes']) !== 78 || $result['cases'] !== 9 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Ordinary production Socket output assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
