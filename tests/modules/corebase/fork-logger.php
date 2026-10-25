<?php
// Actual fork reopens the native logger path in the child. Only owned files
// and an anonymous Process pipe are used; no shared logger path is touched.
function logger_require(bool $value, string $message): void {
    if (!$value) throw new RuntimeException($message);
}
function logger_payloads(string $path): array {
    $raw = file_get_contents($path);
    logger_require(is_string($raw), 'read complete raw logger file');
    preg_match_all('/^\[[^\r\n]+\]\tINFO\t([^\r\n]*)\n/m', $raw, $matches);
    logger_require(implode('', $matches[0]) === $raw, 'all raw lines have native INFO framing');
    return $matches[1];
}
$root = $argv[1];
logger_require(is_dir($root), 'owned outer artifact directory');
foreach ([false, true] as $coroutine) {
    $folder = $root . ($coroutine ? '/coroutine' : '/plain');
    logger_require(mkdir($folder, 0700), 'fresh private logger directory');
    $active = $folder . '/active.log';
    $rotated = $folder . '/rotated.log';
    logger_require(swoole_async_set(['log_file' => $active, 'log_level' => SWOOLE_LOG_INFO]), 'open private logger');
    try {
        swoole_error_log(SWOOLE_LOG_INFO, 'parent-before-fork');
        logger_require(rename($active, $rotated), 'rotate only private log pathname');
        $process = new Swoole\Process(static function (Swoole\Process $child): void {
            swoole_error_log(SWOOLE_LOG_INFO, 'child-after-reopen');
            logger_require($child->write('ready') === 5, 'child log write acknowledged');
        }, false, SOCK_DGRAM, $coroutine);
        $pid = $process->start();
        logger_require(is_int($pid) && $pid > 0, 'actual normal fork');
        logger_require($process->read(64) === 'ready', 'parent receives child acknowledgement');
        $wait = Swoole\Process::wait(true);
        logger_require($wait['pid'] === $pid && $wait['code'] === 0 && $wait['signal'] === 0, 'own child reaped');
        $process->close();
        swoole_error_log(SWOOLE_LOG_INFO, 'parent-after-child');
        logger_require(logger_payloads($rotated) === ['parent-before-fork', 'parent-after-child'],
            'parent retains old file handle across child reopen');
        logger_require(logger_payloads($active) === ['child-after-reopen'],
            'child writes only newly opened pathname');
    } finally {
        // Keep both complete files as evidence, but release the parent's stream.
        logger_require(swoole_async_set(['log_file' => '/dev/null']), 'release private logger');
    }
}
echo "M19 PHP fork logger ownership OK\n";
