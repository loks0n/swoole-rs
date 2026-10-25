<?php
$r=swr_ownership_production();
$labels=['copy prior owner freed','copy free observes live metadata','copy publishes source','copy retains source','self copy no disposal',
    'move prior owner freed','move free observes live metadata','move transfers owner','move source reset','self move no disposal',
    'destructor frees owner','destructor free observes live metadata','all owners reclaimed'];
if(count($r['outcomes'])!==count($labels)) throw new RuntimeException('Ownership assertion inventory differs');
foreach($labels as $i=>$label) if($r['outcomes'][$i]!==true) throw new RuntimeException($label);
$images=[];
if(!is_string($r['method_image'])||!is_string($r['move_image'])) throw new RuntimeException('Actual assignment methods unavailable');
$images['move']=realpath($r['move_image']);$selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    foreach(['dispose_image','plan_image'] as $name) {
        if(!is_string($r[$name])||!realpath($r[$name])) throw new RuntimeException('Selected ownership origin unavailable: '.$name);
        $images[$name]=realpath($r[$name]);++$selectedOriginChecks;
    }
}
echo json_encode(['checks'=>count($labels),'selected_origin_checks'=>$selectedOriginChecks,
    'method_image'=>realpath($r['method_image']),'additional_method_images'=>(object)$images,
    'scope'=>'positive actual assignments and live metadata before native free; no released-byte access, complete lifetime/parity or performance claim']),"\n";
