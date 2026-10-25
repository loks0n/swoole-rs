<?php
$result = swr_reactor_builtins_supported();
if (count($result['outcomes']) !== 31 || in_array(false, $result['outcomes'], true)) {
    throw new RuntimeException('Supported production builtin assertions failed: ' . json_encode($result));
}
$result['checks'] = count($result['outcomes']);
unset($result['outcomes']);
echo json_encode($result), "\n";
