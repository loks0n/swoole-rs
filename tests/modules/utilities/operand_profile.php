<?php
$result = m14_macro_profile($argv[1]);
$records = file($argv[1] . '/macro.log');
if (count($records) !== $result['formats'] + 2) { throw new RuntimeException('exact operand record count'); }
$result['records'] = count($records);
echo json_encode($result, JSON_THROW_ON_ERROR), "\n";
