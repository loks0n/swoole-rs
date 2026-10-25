<?php
$checks=0;
function split_check($actual,$expected,string $label): void {
    global $checks;
    if($actual!==$expected)throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_split_production();
foreach(['false_frame'=>"xxone\r\n",'false_result'=>-1,'false_offset'=>3,'throw_caught'=>true,'throw_offset'=>4,
         'append_packets'=>["one\r\n","two\r\n"],'append_result'=>10,'append_offset'=>10,
         'mutated_packets'=>["a\r\n","c\r\n"],'mutated_result'=>6,'mutated_offset'=>6,
         'offset_callbacks'=>1,'offset_result'=>6,'offset_offset'=>6,
         'binary_packets'=>["a\0b\r\n"],'binary_result'=>5,'binary_offset'=>5,'residual'=>'trail','residual_offset'=>0] as $name=>$expected)split_check($r[$name],$expected,$name);
$images=[];$selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS')&&(SWOOLE_RS_FEATURE_BITS&2)) {
    if($r['plan_image']===null)throw new RuntimeException('Selected continuation planner unavailable');
    $images['plan']=realpath($r['plan_image']);++$selectedOriginChecks;
}
echo json_encode(['checks'=>$checks,'selected_origin_checks'=>$selectedOriginChecks,
    'method_image'=>realpath($r['method_image']),'additional_method_images'=>(object)$images,
    'scope'=>'positive actual production split callback continuations; no short/invalid/overflow or stopped original probe, full lifetime or performance claim']),"\n";
