<?php
$r=swr_format_production();
if($r['checks']!==604) throw new RuntimeException('Whole formatter assertion inventory differs');
if(!is_string($r['method_image'])||!is_string($r['alloc_image'])) throw new RuntimeException('Actual native allocation methods unavailable');
$images=['alloc'=>realpath($r['alloc_image'])];$selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    foreach(['step_image','plan_image'] as $name) {
        if(!is_string($r[$name])||!realpath($r[$name])) throw new RuntimeException('Selected formatter origin unavailable: '.$name);
        $images[$name]=realpath($r[$name]);++$selectedOriginChecks;
    }
}
echo json_encode(['checks'=>$r['checks'],'selected_origin_checks'=>$selectedOriginChecks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'whole source-qualified format/append-format workflow over actual loaded methods with stable positive args; no stopped domains/full parity/performance claim']),"\n";
