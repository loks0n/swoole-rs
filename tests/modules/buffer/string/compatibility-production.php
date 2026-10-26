<?php
$r=swr_compatibility_production();
if($r['checks']!==44) throw new RuntimeException('Ordinary compatibility44 inventory differs');
if(!is_string($r['method_image'])||!realpath($r['method_image'])) throw new RuntimeException('Actual Native append origin unavailable');
$images=[];$selectedOriginChecks=0;
foreach(['repeat_image','write_image','copy_image','integer_image','reduce_image'] as $key) {
    if(!is_string($r[$key])||!realpath($r[$key])) throw new RuntimeException('Actual Native consumer unavailable: '.$key);
    $images[$key]=realpath($r[$key]);
}
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    if(!is_string($r['compat_image'])||!realpath($r['compat_image'])) throw new RuntimeException('Actual selected continuation unavailable');
    $images['compat_image']=realpath($r['compat_image']);++$selectedOriginChecks;
}
echo json_encode(['checks'=>$r['checks'],'selected_origin_checks'=>$selectedOriginChecks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'Exact44ordinaryappend/write/i32/repeat/copy/termination/reduce loaded caller; no custom allocator/callback/failure/POP/destruction/lifetime probe or full parity/performance claim']),"\n";
