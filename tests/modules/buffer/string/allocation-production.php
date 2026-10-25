<?php
$r=swr_allocation_production();
$labels=['copy initial metadata before malloc','copy fresh source','copy capacity/provenance','aligned reserve capacity',
    'reserve native offset effect','reserve value/provenance','caught reserve OOM','failed reserve prefix','custom owner custody',
    'empty reserve metadata','empty reserve native allocator','initial aligned allocation'];
if(count($r['outcomes'])!==count($labels)) throw new RuntimeException('Allocation assertion inventory differs');
foreach($labels as $i=>$label) if($r['outcomes'][$i]!==true) throw new RuntimeException($label);
if(!is_string($r['method_image'])||!is_string($r['reserve_image'])) throw new RuntimeException('Actual allocation methods unavailable');
$images=['reserve'=>realpath($r['reserve_image'])];$selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    if(!is_string($r['plan_image'])||!realpath($r['plan_image'])) throw new RuntimeException('Selected allocation plan unavailable');
    $images['plan']=realpath($r['plan_image']);++$selectedOriginChecks;
}
echo json_encode(['checks'=>count($labels),'selected_origin_checks'=>$selectedOriginChecks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'positive actual allocation effects/publication, offset-only native effect and caught reserve OOM; no stopped unsafe domain or full parity/performance claim']),"\n";
