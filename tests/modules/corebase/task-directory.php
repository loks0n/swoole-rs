<?php
// Defined settings and valid packets only. Rejected paths retain a valid template;
// no oversized template is consumed. A private loopback socket is bound but never
// listened on; no workers, shared fixture paths or task packet layout assumptions.
use Swoole\Server\Task;

function require_task($condition, string $label): void {
    if (!$condition) { throw new RuntimeException($label); }
}
function task_files(string $directory): array {
    $files = glob($directory . '/*');
    require_task(is_array($files), 'read task directory');
    sort($files);
    return $files;
}
function roundtrip_task($value, string $directory, bool $fileBacked): void {
    require_task(task_files($directory) === [], 'empty before pack');
    $packed = Task::pack($value);
    require_task(is_string($packed), 'pack returned packet');
    $files = task_files($directory);
    require_task(count($files) === ($fileBacked ? 1 : 0), 'file-backed threshold');
    if ($fileBacked) {
        require_task(is_file($files[0]) && filesize($files[0]) > 8192, 'actual task data file');
    }
    require_task(Task::unpack($packed) === $value, 'exact unpacked value');
    require_task(task_files($directory) === [], 'unpack removed file');
}
$startup = ($argv[1] ?? '') === 'startup';
$errors = ($argv[1] ?? '') === 'settings-error';
$root = $startup ? $argv[2] : sys_get_temp_dir() . '/swr-m19-task-' . bin2hex(random_bytes(12));
if ($startup) {
    require_task(ini_get('sys_temp_dir') === $root && sys_get_temp_dir() === $root,
        'actual configured startup temporary directory');
    require_task(is_dir($root), 'RINIT created configured directory before script');
} else {
    require_task(mkdir($root, 0700), 'private root');
}
$server = null;
$warningLog = null;
try {
    if ($startup) {
        roundtrip_task(str_repeat("startup\0\xff", 32768), $root, true);
        echo "M19 PHP task directory startup OK\n";
        return;
    }
    $server = new Swoole\Server('127.0.0.1', 0, SWOOLE_BASE, SWOOLE_SOCK_TCP);
    $first = $root . '/first/child';
    require_task($server->set(['task_tmpdir' => $first]), 'first task_tmpdir setting');
    require_task(is_dir($first), 'recursive task directory creation');
    $large = str_repeat("task\0\xff\x01", 32768);
    if ($errors) {
        $expectedError = (int) $argv[2];
        $warningLog = $root . '/warnings.log';
        require_task($server->set(['log_file' => $warningLog, 'log_level' => SWOOLE_LOG_WARNING]) === true,
            'configure private warning logger');
        swoole_clear_error();
        require_task($server->set(['task_tmpdir' => 'relative']) === true,
            'Server::set discards relative setter rejection');
        require_task(swoole_last_error() === 0, 'ordinary warning preserves last_error');
        roundtrip_task($large, $first, true);
        $parent = $root . '/parent-file';
        require_task(file_put_contents($parent, 'parent') === 6, 'regular-file parent');
        $bad = $parent . '/child';
        require_task($server->set(['task_tmpdir' => $bad]) === true,
            'Server::set discards mkdir setter rejection');
        require_task(swoole_last_error() === $expectedError && $server->getLastError() === $expectedError,
            'real ENOTDIR published through both public error observers');
        require_task(!is_dir($bad), 'failed path not created');
        roundtrip_task($large, $first, true);
        $text = swoole_strerror($expectedError, SWOOLE_STRERROR_SYSTEM);
        require_task(swoole_strerror($expectedError, SWOOLE_STRERROR_SWOOLE) === $text,
            'forced native/selected Swoole error dispatcher matches independent libc text');
        $raw = file_get_contents($warningLog);
        require_task(is_string($raw), 'read private warnings');
        $payloads = preg_replace('/^\[[^\r\n]*\]\t/m', '', $raw);
        // PHP's explicit SYSTEM strerror is a native libc text oracle. It is
        // not proof that this call itself traverses the selected Rust resolver.
        require_task($payloads === "WARNING\tswoole_set_task_tmpdir(): wrong absolute path 'relative'\n"
            . "WARNING\tswoole_mkdir_recursive(): mkdir('$bad') failed, Error: $text" . "[$expectedError]\n"
            . "WARNING\tswoole_set_task_tmpdir(): create task tmp dir('$bad') failed\n",
            'three exact ordered warnings, no extras or duplicates');
        require_task($server->set(['task_tmpdir' => $parent]) === true, 'readable regular-file setting');
        $phpWarnings = [];
        set_error_handler(static function ($severity, $message) use (&$phpWarnings): bool {
            $phpWarnings[] = [$severity, $message];
            return true;
        });
        try {
            require_task(Task::pack($large) === false, 'accepted file template fails actual tempfile creation');
        } finally {
            restore_error_handler();
        }
        require_task($phpWarnings === [[E_WARNING, 'Swoole\\Server\\Task::pack(): large task pack failed']],
            'exact PHP warning from actual pack failure');
        // The later PHP warning macro replaces the syscall's ENOTDIR code.
        require_task(swoole_last_error() === SWOOLE_ERROR_PHP_FATAL_ERROR
            && $server->getLastError() === SWOOLE_ERROR_PHP_FATAL_ERROR,
            'PHP warning replaces tempfile error code');
        require_task(file_get_contents($parent) === 'parent', 'regular file unchanged');
        require_task($server->set(['task_tmpdir' => $first]) === true, 'restore valid template');
        roundtrip_task($large, $first, true);
        $allRaw = file_get_contents($warningLog);
        require_task(is_string($allRaw) && str_starts_with($allRaw, $raw), 'warning prefix unchanged');
        $tail = preg_replace('/^\[[^\r\n]*\]\t/m', '', substr($allRaw, strlen($raw)));
        require_task(preg_match("~\\AWARNING\\tswoole_tmpfile\\(\\): mkstemp\\('"
            . preg_quote($parent, '~') . "/swoole\\.task\\.[A-Za-z0-9]{6}'\\) failed, Error: "
            . preg_quote($text, '~') . "\\[$expectedError\\]\\n\\z~", $tail) === 1,
            'one exact tempfile warning with native six-character name');
        echo "M19 PHP task directory errors OK\n";
        return;
    }
    roundtrip_task("small\0binary", $first, false);
    roundtrip_task($large, $first, true);
    roundtrip_task(['data' => $large, 'number' => 123, 'nil' => null], $first, true);
    $second = $root . '/second';
    require_task($server->set(['task_tmpdir' => $second . '/']), 'replace task_tmpdir setting');
    require_task(is_dir($second), 'second task directory creation');
    roundtrip_task($large, $second, true);
    require_task(task_files($first) === [], 'old task directory stays empty');
    echo "M19 PHP task directory consumers OK\n";
} finally {
    if ($errors && $warningLog !== null && is_file($warningLog)) {
        // Preserve warning bytes even when a new assertion fails; this path is
        // supplied by the supervising gate outside the temporary cleanup tree.
        $raw = file_get_contents($warningLog);
        require_task(is_string($raw) && file_put_contents($argv[3], $raw) === strlen($raw),
            'retain full warning stream');
        require_task($server->set(['log_file' => '/dev/null']) === true,
            'close private logger before cleanup');
    }
    unset($server);
    // Only remove entries below this freshly generated private root.
    $entries = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,
        FilesystemIterator::SKIP_DOTS), RecursiveIteratorIterator::CHILD_FIRST);
    foreach ($entries as $entry) {
        $entry->isDir() && !$entry->isLink() ? rmdir($entry->getPathname()) : unlink($entry->getPathname());
    }
    rmdir($root);
}
