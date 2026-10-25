<?php
$checks=0;
function copy_check($actual,$expected,string $label): void {
    global $checks;
    if($actual!==$expected) throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_copy_production();
foreach(['copied','source_after_copy_write','assigned','source_after_oom','fresh_custom_copy','borrowed_copy'] as $name) {
    copy_check($r[$name]['bytes'],"a\0b",$name.' initialized binary bytes');
    copy_check($r[$name]['length'],3,$name.' length');
    copy_check($r[$name]['capacity'],$name==='borrowed_copy'?8:16,$name.' capacity');
    copy_check($r[$name]['offset'],in_array($name,['borrowed_copy','fresh_custom_copy'],true)?1:2,$name.' offset');
    copy_check($r[$name]['custom_allocator'],$name!=='borrowed_copy',$name.' custom provenance');
}
foreach(['copy_independent','self_copy_same_owner','constructor_oom_caught','borrowed_copy_standard',
         'borrowed_independent','source_stays_borrowed','custom_source_offset_effect'] as $name) copy_check($r[$name],true,$name);
foreach(['assignment_effects'=>'FM','self_copy_effects'=>0,'constructor_oom_effects'=>'M',
         'native_allocations'=>5,'native_frees'=>5] as $name=>$expected) copy_check($r[$name],$expected,$name);
$images=['assignment'=>realpath($r['assignment_image'])]; $selectedOriginChecks=0;
if(defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    foreach(['system_image','apply_image'] as $name) {
        if($r[$name]===null) throw new RuntimeException('Selected COPY editor unavailable: '.$name);
        $images[$name]=realpath($r[$name]); ++$selectedOriginChecks;
    }
}
echo json_encode(['checks'=>$checks,'selected_origin_checks'=>$selectedOriginChecks,
    'method_image'=>realpath($r['method_image']),'additional_method_images'=>(object)$images,
    'scope'=>'positive actual production copy/assignment, custom provenance and caught constructor OOM; no private native/zero/unsafe probes or full lifetime/performance claim']),"\n";
