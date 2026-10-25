<?php
$checks=0;
function terminator_check($actual,$expected,string $label):void{
    global $checks;
    if($actual!==$expected)throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_terminator_production();
foreach(['spare'=>['abc',8,1,false],'full'=>['12345678',16,1,false],
         'borrowed'=>['abc',8,1,true],'text_constructor'=>['abc',8,0,false],
         'binary_constructor'=>["a\0b",8,0,false]]as$name=>$expected){
    terminator_check($r[$name]['bytes'],$expected[0],$name.' initialized bytes');
    terminator_check($r[$name]['length'],strlen($expected[0]),$name.' length');
    terminator_check($r[$name]['capacity'],$expected[1],$name.' capacity');
    terminator_check($r[$name]['offset'],$expected[2],$name.' offset');
    terminator_check($r[$name]['allocator_null'],$expected[3],$name.' allocator custody');
    terminator_check($r[$name]['terminator'],0,$name.' trailing NUL');
}
terminator_check($r['borrowed_pointer_same'],true,'borrowed pointer retained');
terminator_check($r['borrowed_bytes_after_destructor'],true,'borrowed storage not freed');
terminator_check($r['native_allocations'],2,'custom native allocations');
terminator_check($r['native_frees'],2,'custom native disposals');
$images=[];
if(defined('SWOOLE_RS_FEATURE_BITS')&&(SWOOLE_RS_FEATURE_BITS&2)){
    if($r['terminator_image']===null)throw new RuntimeException('Selected production terminator method unavailable');
    $images['terminator']=realpath($r['terminator_image']);
}
echo json_encode(['checks'=>$checks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'positive loaded owned/full/spare and borrowed-spare NUL consumers plus constructors; no unsafe borrowed-full/zero-owner/overflow, whole parity or performance claim']),"\n";
