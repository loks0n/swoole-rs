#!/usr/bin/env python3
"""Instrument the selected native timer adapter; unchanged baseline probe goldens."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
SCENARIOS = ['equal-deadlines', 'self-remove', 'remove-other', 'destructor-remove-other',
             'update-active-repeat', 'destructor-add', 'fork-teardown',
             'delay-active-once', 'nested-select-once']

EXCEPTION_SCENARIOS = ['callback-throws', 'destructor-throws', 'callback-destructor-throw']

EXPECTED = {
    'equal-deadlines': ('AaCcBb', 'AaCcBb', 0, 3, False),
    'self-remove': ('AYNVa', 'AYNVa', 0, 1, False),
    'remove-other': ('AbaCc', 'AbaCc', 0, 3, False),
    'destructor-remove-other': ('AabCc', 'AabCc', 0, 3, False),
    'update-active-repeat': ('ABb', 'ABba', 1, 2, True),
    'destructor-add': ('AaBb', 'AaBbCc', 1, 3, False),
    'delay-active-once': ('AaBb', 'AaBb', 0, 2, False),
    'nested-select-once': ('Aa', 'Aa', 0, 1, False),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, detail):
    if not value:
        raise AssertionError(detail)


def verify(name, observations):
    finals = [value for value in observations if value.get('scenario') == name and 'phase' not in value]
    require(len(finals) == 1, f'{name}: one final observation required: {observations}')
    value = finals[0]
    if name == 'wrapper-clear':
        require(value == {'scenario': name, 'inactive': True, 'missing': True, 'active': True,
                          'cancelled_other': True, 'active_view': True, 'remaining': 0,
                          'events': 'cAba', 'destructors': 3}, value)
        return
    if name in EXCEPTION_SCENARIOS:
        require(value == {'scenario': name, 'failure': 'destructor' if name == 'destructor-throws' else 'callback',
                          'survivor_intact': True, 'remaining': 0, 'events': 'AaBb', 'destructors': 2}, value)
        return
    if name == 'fork-active-teardown':
        require(value == {'scenario': name, 'child_status': 0, 'parent_intact': True, 'parent_drained': True, 'parent_destructors': 2}, value)
        return
    if name == 'fork-teardown':
        require(value == {'scenario': name, 'child_status': 0, 'parent_intact': True, 'parent_destructors': 1}, value)
        return
    second, events, count, destructors, a_present = EXPECTED[name]
    expected = {'scenario': name, 'after_first': '', 'after_second': second, 'events': events,
                'count_after_second': count, 'destructors': destructors,
                'a_present': a_present, 'b_present': False}
    require(value == expected, f'{name}: expected {expected}, observed {value}')
    phases = [value for value in observations if 'phase' in value]
    require(phases == ([{'phase': 'callback-updated', 'scenario': name}] if name in ['delay-active-once', 'update-active-repeat'] else []),
            f'{name}: phase mismatch: {phases}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'target/hybrid/rust-timer/build-manifest.json')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[], help='Extra PHP module loaded before Swoole; Linux adds ffi if not built in')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/timer-adapter.json'))
    args = parser.parse_args()
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False, 'platform': platform.platform(),
              'upstream_commit': PIN, 'scenarios': [],
              'scope': 'Selected immutable native timer adapter and ID wrapper plus baseline probe and selected Rust archive. No heap.cc compiled. Native caller/adapter ASan+UBSan when selected; Rust archive, PHP and runtime dependencies uninstrumented. Fourteen isolated five-second scenario process groups, including callback/destructor exception cleanup. Original failed upstream baseline reports remain failures.'}
    try:
        require(sys.platform == 'darwin' or sys.platform.startswith('linux'), 'Native adapter probe supports macOS and Linux only')
        linux = sys.platform.startswith('linux')
        php_extensions = list(args.php_extension)
        builtin_ffi = subprocess.check_output([args.php, '-n', '-r', 'echo extension_loaded("FFI") ? "yes" : "no";'], text=True, timeout=10).strip() == 'yes'
        if linux and not builtin_ffi and not any(Path(value).stem.lower() == 'ffi' for value in php_extensions):
            php_extensions.insert(0, 'ffi')
        php_extra = [value for module in php_extensions for value in ['-d', 'extension=' + module]]
        report['php_extensions'] = php_extensions
        manifest_path = args.manifest.resolve(strict=True)
        manifest = json.loads(manifest_path.read_text())
        require(manifest['build_mode'] == 'immutable', 'immutable build required')
        require(manifest['inputs']['upstream_commit'] == PIN and 'timer' in manifest['inputs']['modules'], 'wrong selected source')
        extension = Path(manifest['extension']).resolve(strict=True)
        source = extension.parents[1]
        prefix = extension.parents[2] / 'rust-prefix'
        archive = prefix / 'lib/libswoole_rs_ffi.a'
        require(sha(extension) == manifest['extension_sha256'], 'extension checksum mismatch')
        require(sha(archive) == manifest['inputs']['rust_archive_sha256'], 'archive checksum mismatch')
        actual_pin = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        diff = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=source, text=True).strip()
        require(actual_pin == PIN and hashlib.sha256(diff.encode()).hexdigest() == manifest['source_diff_sha256'], 'source diff/pin mismatch')
        for name, checksum in manifest['inputs']['headers_sha256'].items():
            require(sha(prefix / 'include' / Path(name).name) == checksum, f'ABI header mismatch: {name}')
        report.update({'manifest_path': str(manifest_path), 'extension': str(extension), 'archive': str(archive)})
        with tempfile.TemporaryDirectory(prefix='swr-timer-adapter-') as directory:
            tree = Path(directory)
            names = subprocess.check_output(['git', 'ls-files', 'include'], cwd=source, text=True).splitlines() + ['src/core/timer.cc', 'src/wrapper/timer.cc']
            for name in names:
                original = source / name
                if original.is_file():
                    destination = tree / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original, destination)
            library = tree / ('probe.so' if linux else 'probe.dylib')
            compiler = shlex.split(os.environ.get('CXX', 'c++'))
            linker_flags = ['-shared', '-fPIC', '-Wl,-Bsymbolic'] if linux else ['-dynamiclib', '-undefined', 'dynamic_lookup']
            selected_defines = ['-DSWOOLE_RS_' + module.upper() + '=1' for module in manifest['inputs']['modules']]
            command = compiler + ['-std=c++17', '-O1', '-g', *linker_flags,
                                  *selected_defines, '-I' + str(tree / 'include'), '-I' + str(prefix / 'include')]
            command += shlex.split(manifest['inputs']['effective_cppflags'])
            for option in manifest['configure']:
                if option.startswith('--with-openssl-dir='):
                    command += ['-I' + option.split('=', 1)[1] + '/include']
            command += [str(tree / 'src/core/timer.cc'), str(tree / 'src/wrapper/timer.cc'), str(Path(__file__).with_name('probe.cc')), str(archive), '-lc', '-lm']
            if linux:
                command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            command += ['-o', str(library)]
            environment = dict(os.environ)
            if args.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
                runtime_name = 'libasan.so' if linux else 'libclang_rt.asan_osx_dynamic.dylib'
                runtime = Path(subprocess.check_output(compiler + ['--print-file-name=' + runtime_name], text=True).strip()).resolve()
                require(runtime.is_file(), f'ASan runtime absent: {runtime}')
                environment.update({'LD_PRELOAD' if linux else 'DYLD_INSERT_LIBRARIES': str(runtime),
                    'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1:abort_on_error=0:exitcode=86:log_path=' + str(tree / 'asan-report'),
                    'UBSAN_OPTIONS': 'print_stacktrace=1:halt_on_error=1:exitcode=87'})
                report['sanitizer_runtime'] = str(runtime)
                report['sanitizer_options'] = {key: environment[key] for key in ['ASAN_OPTIONS', 'UBSAN_OPTIONS']}
            report['compile_command'] = command
            compiled = run_isolated(command, timeout=45)
            report['compile'] = {'returncode': compiled.returncode, 'stdout': compiled.stdout, 'stderr': compiled.stderr}
            require(compiled.returncode == 0, compiled.stderr)
            php = '$ffi=FFI::cdef("int swr_timer_probe(const char *name);", $argv[1]); exit($ffi->swr_timer_probe($argv[2]));'
            for name in [*SCENARIOS, 'fork-active-teardown', *EXCEPTION_SCENARIOS, 'wrapper-clear']:
                row = {'name': name, 'passed': False}
                try:
                    result = run_isolated([args.php, '-n', *php_extra, '-d', 'extension=' + str(extension), '-d', 'ffi.enable=1',
                                           '-r', php, str(library), name], timeout=5, env=environment)
                    row.update({'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'observations': []})
                    for line in result.stdout.splitlines():
                        try:
                            row['observations'].append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                    require(result.returncode == 0, f'process exit {result.returncode}')
                    verify(name, row['observations'])
                    row['passed'] = True
                except PermissionError as error:
                    row['error'] = f'PermissionError during isolated process-group cleanup: {error}'
                    report['sanitizer_logs'] = {path.name: path.read_text(errors='replace') for path in tree.glob('asan-report*')}
                    report['scenarios'].append(row)
                    raise  # Preserve cleanup failures; do not bypass process-group cleanup.
                except subprocess.TimeoutExpired as error:
                    row.update({'error': f'TimeoutExpired: {error}', 'limit_seconds': 5,
                                'stdout': str(error.stdout), 'stderr': str(error.stderr)})
                except Exception as error:
                    row['error'] = f'{type(error).__name__}: {error}'
                report['scenarios'].append(row)
                report['sanitizer_logs'] = {path.name: path.read_text(errors='replace') for path in tree.glob('asan-report*')}
                write_report(args.output, report)
            report['php'] = subprocess.check_output([args.php, '-n', '-r', 'echo PHP_VERSION;'], text=True)
            report['passed'] = len(report['scenarios']) == 14 and all(row['passed'] for row in report['scenarios']) and not report.get('sanitizer_logs')
    except Exception as error:
        report['framework_failure'] = f'{type(error).__name__}: {error}'
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'scenarios': [(row['name'], row['passed']) for row in report['scenarios']],
                      'framework_failure': report.get('framework_failure')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
