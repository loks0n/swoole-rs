<?php
$checks=0;
function integer_check($actual,$expected,string $label): void {
    global $checks;
    if($actual!==$expected) throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_integer_production();$i=0;
foreach([false,true] as $custom) {
    foreach([-2147483648,-123456789,-1,0,1,2147483647] as $value) {
        foreach([0,2,11,16] as $spare) {
            $row=$r['rows'][$i++];$expected=str_repeat('a',32-$spare).$value;$n=strlen($expected);
            integer_check($row['bytes'],$expected,'decimal bytes');
            integer_check($row['length'],$n,'exact length');
            integer_check($row['capacity'],$n>32?($n+7)&~7:32,'exact capacity');
            integer_check($row['offset'],1,'retained offset');
            integer_check($row['provenance'],true,'allocator provenance');
            integer_check($row['reallocations'],(int)($custom&&$n>32),'exact realloc count');
        }
    }
}
integer_check(count($r['rows']),48,'exact case count');
integer_check($r['failure_caught'],true,'caught realloc failure');
integer_check($r['failure_unchanged'],true,'failure prefix');
integer_check($r['after_failure'],'prefix-7','append after failure');
integer_check($r['allocations'],25,'custom owners');
integer_check($r['frees'],25,'custom owner cleanup');
integer_check($r['reallocations'],10,'custom realloc attempts');
$images=[];$selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    foreach(['swr_v1_string_edit_system','swr_v1_string_apply'] as $name) {
        if(!is_string($r[$name])||!realpath($r[$name])) throw new RuntimeException('Selected integer editor unavailable: '.$name);
        $images[$name]=realpath($r[$name]);++$selectedOriginChecks;
    }
}
echo json_encode(['checks'=>$checks,'selected_origin_checks'=>$selectedOriginChecks,
    'method_image'=>realpath($r['method_image']),'additional_method_images'=>(object)$images,
    'scope'=>'positive actual production integer append/storage with exact native allocation prefix; no full parity or performance claim']),"\n";
