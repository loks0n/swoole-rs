<?php
$checks = 0;
function storage_check($actual, $expected, string $label): void {
    global $checks;
    if ($actual !== $expected) {
        throw new RuntimeException($label . ': ' . var_export($actual, true) . ' != ' . var_export($expected, true));
    }
    ++$checks;
}
$result = swr_storage_production();
$s = $result['strings'];
foreach (['append'=>"a\0b-42", 'write_repeat'=>'axy-42Q!Q!Q!', 'reduce'=>'y-42Q!Q!Q!',
          'pop'=>'42Q!Q!Q!', 'copied'=>'42Q!Q!Q!Z', 'copy_source'=>'42Q!Q!Q!',
          'moved'=>'42Q!Q!Q!Z', 'move_source'=>'', 'format'=>'n=7/x|03'] as $name=>$expected) {
    storage_check($s[$name]['bytes'], $expected, $name . ' exact binary value');
    storage_check($s[$name]['length'], strlen($expected), $name . ' length');
    storage_check($s[$name]['offset'], 0, $name . ' offset');
}
storage_check($s['append']['capacity'], 64, 'append capacity');
storage_check($s['write_repeat']['capacity'], 64, 'no-grow repeat capacity');
storage_check($s['pop']['capacity'], 32, 'pop capacity');
storage_check($s['move_source']['owner_null'], true, 'move source relinquished owner');
storage_check($s['move_source']['capacity'], 0, 'move source capacity');
storage_check($s['detached'], 'y-42Q!Q!Q!', 'old owner bytes before native free');
storage_check($s['split'], ['aa|','bb|'], 'ordinary complete delimiter callbacks');
storage_check($s['split_consumed'], 6, 'complete split consumed');
storage_check($s['split_offset'], 6, 'complete split offset');
$b = $result['buffers'];
storage_check($b['front_stable'], true, 'cached front identity survives append');
storage_check($b['front_offset'], 2, 'cached front offset survives append');
storage_check($b['before_length'], 11, 'appended byte accounting');
storage_check($b['before_count'], 4, 'chunk count');
storage_check($b['drained'], "23\0abcdXY", 'drained partial first view');
storage_check($b['lengths_after_pop'], [7,3,2,0], 'whole entry accounting after partial sends');
storage_check($b['final_count'], 0, 'drain queue empty');
storage_check($b['vector_length'], 8, 'positive offset-zero vector length');
storage_check($b['vector_count'], 2, 'positive vector chunk count');
storage_check($b['vector_bytes'], "a\0bcdefg", 'positive vector binary bytes');
storage_check($b['vector_final_length'], 0, 'positive vector final accounting');
echo json_encode(['checks'=>$checks, 'method_image'=>realpath($result['method_image']),
    'additional_method_images'=>['string_append'=>realpath($result['string_image'])],
    'scope'=>'bounded ordinary actual Buffer/String storage caller supplement; no corrected unsafe edges, allocator/fork/fatal/reentry/performance or full parity claim']), "\n";
