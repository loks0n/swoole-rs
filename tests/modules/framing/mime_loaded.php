<?php
// Ordinary MIME APIs in the actual DSO. No server, socket, parser or callbacks.
$fixture = json_decode(file_get_contents($argv[1]), true, 512, JSON_THROW_ON_ERROR);
$catalog = swoole_mime_type_list();
$rows = [];
foreach ($fixture['catalog'] as [$suffix, $expected, $exists]) {
    foreach (['file.' . $suffix, 'file.' . strtoupper($suffix)] as $filename) {
        $value = swoole_mime_type_get($filename);
        $present = swoole_mime_type_exists($filename);
        if ($value !== $expected || $present !== $exists) throw new RuntimeException('Catalog lookup mismatch');
        $rows[] = [$filename, $value, $present];
    }
}
foreach ($fixture['extra'] as [$filename, $expected, $exists]) {
    $value = swoole_mime_type_get($filename);
    $present = swoole_mime_type_exists($filename);
    if ($value !== $expected || $present !== $exists) throw new RuntimeException('Suffix lookup mismatch');
    $rows[] = [$filename, $value, $present];
}
$key = 'codexpositive54';
$upper = strtoupper($key);
$operations = [];
$operations[] = swoole_mime_type_add($key, 'application/x-first');
$operations[] = swoole_mime_type_get('file.' . $upper);
$operations[] = swoole_mime_type_exists('file.' . $key);
$operations[] = swoole_mime_type_add($key, 'application/x-ignored');
$operations[] = swoole_mime_type_get('file.' . $key);
$operations[] = swoole_mime_type_set($key, 'application/x-second');
$operations[] = swoole_mime_type_get('file.' . $key);
$operations[] = swoole_mime_type_set($upper, 'application/x-uppercase-key');
$operations[] = swoole_mime_type_get('file.' . $upper);
$operations[] = count(swoole_mime_type_list()) - count($catalog);
$operations[] = swoole_mime_type_delete($upper);
$operations[] = swoole_mime_type_get('file.' . $key);
$operations[] = swoole_mime_type_delete($key);
$operations[] = swoole_mime_type_delete($key);
$operations[] = swoole_mime_type_exists('file.' . $key);
$operations[] = swoole_mime_type_get('file.' . $key);
$operations[] = count(swoole_mime_type_list()) - count($catalog);
echo json_encode(['php' => PHP_VERSION, 'zts' => PHP_ZTS, 'swoole' => phpversion('swoole'),
    'catalog' => $catalog, 'rows' => $rows, 'operations' => $operations], JSON_THROW_ON_ERROR), "\n";
