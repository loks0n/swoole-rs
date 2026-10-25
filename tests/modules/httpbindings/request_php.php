<?php
// Actual Request factory, option conversion/reentry, form and multipart consumers.
Swoole\Coroutine::set(['log_level' => SWOOLE_LOG_NONE]);
$events = [];
$warnings = [];
set_error_handler(static function ($level, $message) use (&$warnings) {
    $warnings[] = [$level, $message];
    return true;
});
class BindingOptionString {
    public function __toString(): string {
        global $events;
        $nested = Swoole\Http\Request::create(['parse_cookie' => false]);
        $nested->parse("GET /nested HTTP/1.1\r\nHost: test\r\nCookie: nested=1\r\n\r\n");
        $events[] = ['nested_cookie' => $nested->cookie];
        return getenv('TEST_DATA');
    }
}
function requestInput(string $mode): string {
    $form = 'one=first&one=last&two=%00binary';
    $header = "POST /binding?query=one HTTP/1.1\r\nHost: test\r\nCookie: a=1; b=two\r\n";
    if ($mode === 'chunked') {
        return $header . "Content-Type: application/x-www-form-urlencoded\r\nTransfer-Encoding: chunked\r\n\r\n" .
            dechex(strlen($form)) . "\r\n" . $form . "\r\n0\r\n\r\n";
    }
    if ($mode === 'multipart') {
        $body = "\r\n\r\n--binding-boundary\r\nContent-Disposition: form-data; name=\"field\"\r\n\r\nvalue\r\n" .
            "--binding-boundary\r\nContent-Disposition: form-data; name=\"upload\"; filename=\"binary.bin\"\r\n" .
            "Content-Type: application/octet-stream\r\n\r\nbinary\0bytes\r\n--binding-boundary--\r\n";
        return $header . "Content-Type: multipart/form-data; boundary=binding-boundary\r\nContent-Length: " . strlen($body) . "\r\n\r\n" . $body;
    }
    return $header . "Content-Type: application/x-www-form-urlencoded\r\nContent-Length: " . strlen($form) . "\r\n\r\n" . $form;
}
$rows = [];
$keys = ['parse_cookie','parse_body','parse_files','enable_compression','compression_level','websocket_compression','upload_tmp_dir','unknown'];
$values = [null, false, true, 0, 1, '', '1', new BindingOptionString()];
foreach ($keys as $name) foreach ([$name, strtoupper($name), $name . "\0"] as $key) {
    foreach ($values as $index => $value) foreach (['form','chunked','multipart'] as $mode) {
        $events = $warnings = [];
        $options = ['upload_tmp_dir' => getenv('TEST_DATA')];
        $options[$key] = $value;
        $request = Swoole\Http\Request::create($options);
        $raw = requestInput($mode);
        $consumed = $request->parse($raw);
        if ($request->getData() !== $raw) throw new RuntimeException('Raw request byte witness');
        $files = $request->files ?? [];
        $paths = [];
        foreach ($files as &$file) {
            if ($file['tmp_name'] !== '') $paths[] = $file['tmp_name'];
            $file['sha256'] = $file['tmp_name'] !== '' ? hash_file('sha256', $file['tmp_name']) : null;
            unset($file['tmp_name']);
        }
        unset($file);
        $rows[] = ['key' => bin2hex($key), 'value' => $index, 'mode' => $mode,
            'consumed' => $consumed, 'completed' => $request->isCompleted(), 'method' => $request->getMethod(),
            'content' => bin2hex($request->getContent()), 'data' => bin2hex($request->getData()),
            'cookie' => $request->cookie, 'post' => $request->post, 'get' => $request->get,
            'files' => $files, 'events' => $events, 'warnings' => $warnings];
        unset($request);
        foreach ($paths as $path) if (file_exists($path)) throw new RuntimeException('Request upload was not removed');
    }
}
function witness(array $rows, string $key, int $value, string $mode): array {
    foreach ($rows as $row) if ($row['key'] === bin2hex($key) && $row['value'] === $value && $row['mode'] === $mode) return $row;
    throw new RuntimeException('Missing witness');
}
if (witness($rows, 'parse_cookie', 1, 'form')['cookie'] !== null ||
    witness($rows, 'parse_cookie', 2, 'form')['cookie'] !== ['a' => '1', 'b' => 'two'] ||
    witness($rows, 'parse_body', 1, 'form')['post'] !== null ||
    witness($rows, 'parse_body', 2, 'chunked')['post'] !== ['one' => 'last', 'two' => "\0binary"] ||
    witness($rows, 'upload_tmp_dir', 7, 'form')['events'] !== [['nested_cookie' => null]]) {
    throw new RuntimeException('Original native option/payload/reentry witness');
}
// Native parse_files=false still publishes this multipart file in the pinned source.
$disabled = witness($rows, 'parse_files', 1, 'multipart')['files'];
if (($disabled['upload']['error'] ?? -1) !== 0 || ($disabled['upload']['size'] ?? -1) !== 12) {
    throw new RuntimeException('Original parse_files=false publication witness');
}
restore_error_handler();
echo json_encode(['cases' => count($rows), 'sha256' => hash('sha256', serialize($rows)), 'rows' => $rows], JSON_THROW_ON_ERROR);
