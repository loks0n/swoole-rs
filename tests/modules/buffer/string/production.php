<?php
// Ordinary entropy/Base64 integration only; no deterministic entropy claim.
$checks = 0;
function production_check(bool $condition, string $label): void {
    global $checks;
    if (!$condition) { throw new RuntimeException($label); }
    ++$checks;
}
$result = swr_string_production();
production_check(is_int($result['page_size']) && $result['page_size'] > 0, 'page size');
production_check(count($result['rows']) === 16, 'separate positive-only raw/base64 size cases');
foreach ($result['rows'] as $row) {
    $requested = $row['requested'];
    $encoded = $row['encoded'];
    $encodedLength = 4 * intdiv($requested + 2, 3);
    $expectedLength = 5 + ($encoded ? $encodedLength : $requested);
    $reservation = 5 + $requested + ($encoded ? $encodedLength + 1 : 0);
    $expectedCapacity = $row['initial_capacity'];
    if ($reservation > $expectedCapacity) {
        $expectedCapacity = intdiv(2 * $reservation + $result['page_size'] - 1, $result['page_size']) * $result['page_size'];
    }
    production_check($row['success'] === true, 'ordinary entropy success');
    production_check($row['length'] === $expectedLength, 'exact append length');
    production_check($row['capacity'] === $expectedCapacity, 'exact visible reserve capacity');
    production_check($row['offset'] === 1, 'existing offset preserved');
    production_check(strlen($row['bytes']) === $expectedLength, 'initialized result span');
    production_check(substr($row['bytes'], 0, 5) === "p\0fx\xff", 'binary prefix preserved');
    if ($encoded) {
        $tail = substr($row['bytes'], 5);
        $decoded = base64_decode($tail, true);
        production_check(is_string($decoded) && strlen($decoded) === $requested, 'PHP independent strict decoder length');
        production_check(base64_encode($decoded) === $tail, 'PHP independent canonical encoding');
    }
    production_check($row['next_success'] === true, 'subsequent raw entropy success');
    production_check($row['next_length'] === $expectedLength + 3, 'subsequent append length');
    production_check($row['next_offset'] === 1, 'subsequent offset');
    production_check(substr($row['next_bytes'], 0, $expectedLength) === $row['bytes'], 'prior bytes preserved by next append');
}
echo json_encode(['checks'=>$checks, 'method_image'=>realpath($result['method_image']),
    'scope'=>'separate positive-length actual production String consumer; broader empty-input gate remains FAILED; no entropy byte oracle, short-read/OOM/full fourth-consumer or parity claim']), "\n";
