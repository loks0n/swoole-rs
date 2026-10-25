<?php
$checks=0;
function iovec_check($actual,$expected,string $label): void {
    global $checks;
    if ($actual!==$expected) throw new RuntimeException($label.': '.var_export($actual,true).' != '.var_export($expected,true));
    ++$checks;
}
$r=swr_iovec_production();
iovec_check([$r['iovec_size'],$r['iovec_alignment'],$r['base_offset'],$r['length_offset']],[16,8,0,8],'qualified target C layout');
iovec_check(count($r['cases']),12,'exact positive case inventory');
$index=0;
foreach ([1,8,9,32] as $count) {
    $bytes=''; for ($i=0;$i<$count;++$i) $bytes.="\0".chr($i).chr(255);
    foreach ([0,1,4] as $chunk) {
        $row=$r['cases'][$index++];
        iovec_check([$row['count'],$row['chunk']],[$count,$chunk],'case identity');
        iovec_check($row['initial_length'],strlen($bytes),'initial byte accounting');
        $effective=$chunk ?: PHP_INT_MAX;
        $chunks=$chunk ? intdiv(strlen($bytes)+$chunk-1,$chunk) : 1;
        iovec_check($row['initial_count'],$chunks,'chunk count');
        iovec_check($row['bytes'],$bytes,'exact initialized binary vector bytes');
        $lengths=[]; $remaining=strlen($bytes);
        while ($remaining) { $remaining-=min($remaining,$effective); $lengths[]=$remaining; }
        iovec_check($row['lengths_after_pop'],$lengths,'every pop byte accounting');
        iovec_check($row['final_count'],0,'final queue empty');
    }
}
$images=[];
if (defined('SWOOLE_RS_FEATURE_BITS') && (SWOOLE_RS_FEATURE_BITS & 2)) {
    if ($r['rust_image']===null) throw new RuntimeException('Selected production POSIX vector export unavailable');
    $images['actual_posix_rust']=realpath($r['rust_image']);
}
echo json_encode(['checks'=>$checks,'method_image'=>realpath($r['method_image']),
    'additional_method_images'=>(object)$images,'scope'=>'12 positive loaded POSIX vector callers, offset0/nonempty only; no unsafe original edges, complete lifetime/parity or performance claim']),"\n";
