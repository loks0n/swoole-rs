<?php
$checks=0;
function facade_check($actual,$expected,string $label): void {
    global $checks;
    if ($actual!==$expected) throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_facade_production();
foreach (['cached_identity'=>true,'cached_offset'=>1,'cached_bytes'=>"z\0b",
          'initial_length'=>10,'initial_count'=>5,'data_before_token'=>["z\0b",'cde','fg'],
          'lengths_after_data'=>[7,4,2],'native_identity'=>true,'callbacks_after_pop'=>1,
          'length_after_token'=>2,'tail_bytes'=>'xy','drain_initial_length'=>9,
          'drain_initial_count'=>8,'drain_cached_identity'=>true,
          'close_events'=>[17,31,32],'callback_metadata'=>true] as $name=>$expected) {
    facade_check($r[$name],$expected,$name);
}
$selectedOriginChecks=0;
$images=['destroy'=>realpath($r['destroy_image'])];
if (defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    foreach (['front_image','plan_image','advance_image'] as $name) {
        if ($r[$name]===null) throw new RuntimeException('Selected actual facade method/export unavailable: '.$name);
        $images[$name]=realpath($r[$name]); ++$selectedOriginChecks;
    }
}
echo json_encode(['checks'=>$checks,'selected_origin_checks'=>$selectedOriginChecks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'supported loaded cache/pop/mixed drain with CLOSE-only destroy callbacks; no DATA destruction byte access, failed-profile parity, full lifetime or performance claim']),"\n";
