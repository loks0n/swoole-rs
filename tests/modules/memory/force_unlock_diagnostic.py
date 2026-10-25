#!/usr/bin/env python3
"""Observe the original table OOM scenario; never reclassify its PHPT result."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare
from tools.harness import parse_engines, run_isolated, write_report

# Inserted only after the original child has exited. No native memory is written.
PARENT_OBSERVER = r'''
$diagnostic_row = ['status' => 'unavailable'];
if (is_readable('/proc/self/mem') && is_readable('/proc/self/maps') && PHP_INT_SIZE === 8 && unpack('S', "\x01\x00")[1] === 1) {
    $diagnostic_memory = fopen('/proc/self/mem', 'rb');
    foreach (file('/proc/self/maps') as $mapping) {
        if (!preg_match('/^([0-9a-f]+)-([0-9a-f]+) rw-s /', $mapping, $match)) continue;
        $base = intval($match[1], 16); $end = intval($match[2], 16);
        if ($end - $base < 100 * 1024 * 1024) continue;
        fseek($diagnostic_memory, $base + 8);
        foreach (unpack('Q*', fread($diagnostic_memory, 64 * 8)) as $address) {
            if ($address < $base || $address + 88 >= $end) continue;
            fseek($diagnostic_memory, $address); $header = fread($diagnostic_memory, 88);
            if (ord($header[9]) === 4 && substr($header, 24, 4) === 'test') {
                $diagnostic_row = ['status' => 'observed', 'fields' => unpack('Vlock/Vpid/Cactive/Ckeylen', $header)];
            }
        }
    }
    fclose($diagnostic_memory);
}
fwrite(STDERR, 'M12_DIAGNOSTIC_ROW ' . json_encode($diagnostic_row) . PHP_EOL);
swoole_error_log(SWOOLE_LOG_WARNING, 'M12 diagnostic logger probe');
'''


def prepare_native(args):
    """Build only the test observer, never an upstream library or extension."""
    artifacts = args.output.resolve().with_name(args.output.stem + '-artifacts')
    artifacts.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name('force_unlock_native.c')
    flags = shlex.split(subprocess.check_output([args.php_config, '--includes'], text=True))
    module = artifacts / 'swr_memory_diagnostic.so'
    with tempfile.TemporaryDirectory(prefix='swr-memory-native-observer-') as temporary:
        compiled = Path(temporary) / module.name
        command = [args.cc, '-shared', '-fPIC', '-std=c11', '-Wall', '-Wextra', '-Werror',
                   *flags, str(source), '-o', str(compiled)]
        result = run_isolated(command, timeout=60)
        (artifacts / 'compile.log').write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Native diagnostic compilation failed: ' + str(artifacts / 'compile.log'))
        shutil.copy2(compiled, module)
    shutil.copy2(source, artifacts / source.name)
    return module, {'command': command,
                    'scope': 'Private Linux NTS native get/error callback observer; no production Rust/native code or original test is modified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-trace', action='store_true', help='Compile/load private Linux NTS get/fatal observer')
    parser.add_argument('--php-config', default='php-config')
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    if args.native_trace and sys.platform != 'linux':
        parser.error('--native-trace requires Linux')
    case = 'tests/swoole_table/force_unlock.phpt'
    original = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{COMMIT}:{case}'])
    digest = hashlib.sha256(original).hexdigest()
    body = original.decode().split('--FILE--\n')[1].split('--EXPECTF--')[0]
    capture = "Assert::contains($proc->read(), 'Fatal error: Allowed memory');"
    if body.count(capture) != 1:
        raise ValueError('Pinned capture point changed')
    body = body.replace(capture, "$diagnostic_child = $proc->read(); fwrite(STDERR, 'M12_DIAGNOSTIC_CHILD ' . json_encode(['output' => $diagnostic_child, 'exit' => $exit_status]) . PHP_EOL); Assert::contains($diagnostic_child, 'Fatal error: Allowed memory');\n" + PARENT_OBSERVER)
    if args.native_trace:
        watch = "$table->set('test', $data);"
        if body.count(watch) != 1:
            raise ValueError('Pinned table setup point changed')
        body = body.replace(watch, watch + '\nassert(swr_memory_diag_watch_table());')
    report = {'scope': 'Modified diagnostic copy, not an original PHPT run or replacement gate. Child body/stress parameters unchanged; added parent observations can alter compilation/heap footprint. Linux row observer assumes the pinned 64-bit little-endian mmap/header layout and may be unavailable.',
              'original_phpt_status': 'not_run', 'upstream_commit': COMMIT, 'engines': []}
    module = None
    try:
        if args.native_trace:
            module, report['native_trace'] = prepare_native(args)
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            metadata = engine.metadata()
            if args.native_trace and metadata['zts']:
                raise ValueError('Native observer requires PHP NTS')
            with tempfile.TemporaryDirectory(prefix='swr-memory-force-observer-') as directory:
                sandbox = Path(directory)
                prepare(args.source, sandbox, [{'path': case, 'sha256': digest}])
                script = sandbox / 'tests/swoole_table/force_unlock_diagnostic.php'
                script.write_text(body)
                extra = ['-d', 'extension=' + str(module)] if module else []
                command = engine.command(*extra, '-d', 'zend.assertions=1', '-d', 'display_errors=1', '-d', 'log_errors=0', script)
                result = run_isolated(command, cwd=sandbox, timeout=15, env={**os.environ, 'PHPT': '1'})
                observations = {name.lower(): json.loads(value) for name, value in
                                re.findall(r'^M12_DIAGNOSTIC_(CHILD|ROW) (.+)$', result.stderr, re.MULTILINE)}
                report['engines'].append({**metadata, 'command': command, 'exit_code': result.returncode,
                    'stdout': result.stdout, 'stderr': result.stderr, 'observations': observations,
                    'dead_owner_warning_observed': 'TableRow::lock(): lock process[' in result.stdout,
                    'logger_probe_observed': 'M12 diagnostic logger probe' in result.stdout})
        report['execution_status'] = 'complete'
    except Exception as error:
        report['execution_status'] = 'failed'
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps(report))
    return int(report['execution_status'] != 'complete' or any(row['exit_code'] or set(row['observations']) != {'child', 'row'} for row in report['engines']))


if __name__ == '__main__':
    sys.exit(main())
