<?php
$checks = 0;
function metadata_check($actual, $expected, string $label): void {
    global $checks;
    if ($actual !== $expected) throw new RuntimeException($label . ': ' . var_export($actual, true) . ' != ' . var_export($expected, true));
    ++$checks;
}
$r = swr_metadata_production();
foreach (['clear'=>['',32,0], 'moved'=>["x\0y",32,1], 'move_source'=>['',0,0],
          'released'=>['',0,0], 'assigned'=>['new',16,2], 'assignment_source'=>['',0,0],
          'self_assigned'=>['new',16,2], 'extended'=>['abc',72,0]] as $name=>$expected) {
    metadata_check($r[$name]['bytes'], $expected[0], $name . ' exact bytes');
    metadata_check($r[$name]['length'], strlen($expected[0]), $name . ' length');
    metadata_check($r[$name]['capacity'], $expected[1], $name . ' capacity');
    metadata_check($r[$name]['offset'], $expected[2], $name . ' offset');
    metadata_check($r[$name]['owner_null'], in_array($name,['move_source','released','assignment_source'],true), $name . ' owner null');
    metadata_check($r[$name]['allocator_retained'], true, $name . ' allocator token custody');
}
foreach (['clear_owner_same','move_owner_same','release_owner_same','assignment_owner_same','self_owner_same'] as $name) metadata_check($r[$name],true,$name);
foreach (['free_after_clear','free_after_move','free_before_detached_disposal'] as $name) metadata_check($r[$name],0,$name);
metadata_check($r['detached'], "x\0y", 'detached owner bytes before disposal');
metadata_check($r['assignment_disposals'],1,'destination disposed before owner transfer');
metadata_check($r['assignment_disposals_after_self'],1,'self assignment no disposal');
metadata_check($r['native_allocations'],4,'ordinary positive native allocations');
metadata_check($r['native_frees'],4,'native owners disposed exactly once');
$images = ['move'=>realpath($r['move_image'])];
if (defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    if ($r['transition_image'] === null) throw new RuntimeException('Selected production metadata transition export unavailable');
    $images['transition'] = realpath($r['transition_image']);
}
echo json_encode(['checks'=>$checks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>$images,'scope'=>'positive loaded String ownership consumers; no unsafe zero/overflow, private direct-self access, Rust sanitizer, full parity or performance claim']), "\n";
