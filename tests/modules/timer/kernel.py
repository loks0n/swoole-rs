#!/usr/bin/env python3
"""Real timer queue C ABI gate; injected clock, no PHP/reactor integration claim."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-asan', action='store_true', help='Supplied archive was separately compiled with Rust ASan')
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--archive', type=Path, default=ROOT / 'target/release/libswoole_rs_timer.a')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/timer-kernel.json'))
    args = parser.parse_args()
    if args.rust_asan and not (args.sanitize and args.no_build):
        parser.error('--rust-asan requires --sanitize --no-build and an instrumented archive')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Actual pure Rust queue C ABI with native tokens and injected time; no PHP timer or wakeup integration. ASan/UBSan instruments C/C++ caller only, not Rust archive.',
              'upstream_commit': '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e',
              'caller_sanitized': args.sanitize, 'rust_asan_declared': args.rust_asan,
              'archive_source_identity': 'current source snapshot; archive/source correspondence not independently verified' if args.no_build or args.archive.resolve() != (ROOT / 'target/release/libswoole_rs_timer.a').resolve() else 'default archive built from recorded workspace source in this run',
              'not_exercised': ['ID exhaustion at INT64_MAX', 'round exhaustion at UINT64_MAX',
                                'execution counter exhaustion at UINT64_MAX', 'allocation fault injection',
                                'PHP callbacks, Zend bailout and reactor wakeups', 'multithreaded fork allocator safety'],
              'commands': []}
    env = dict(os.environ)
    if args.sanitize:
        env['ASAN_OPTIONS'] = f'detect_leaks={0 if sys.platform == "darwin" else 1}:abort_on_error=1'
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
        report['sanitizer_options'] = {key: env[key] for key in ['ASAN_OPTIONS', 'UBSAN_OPTIONS']}
    try:
        def run(command, timeout=60):
            result = run_isolated(command, timeout=timeout, cwd=ROOT, env=env)
            report['commands'].append({'argv': command, 'exit_code': result.returncode,
                                       'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode:
                raise RuntimeError(f'command failed ({result.returncode}): {result.stderr}')
            return result
        if not args.no_build:
            run(['cargo', 'build', '-p', 'swoole-rs-timer', '--release', '--locked'], timeout=180)
        archive = args.archive.resolve(strict=True)
        if args.rust_asan:
            symbols = subprocess.run(['nm', '-u', str(archive)], capture_output=True, text=True)
            report['asan_symbol_probe'] = {'returncode': symbols.returncode, 'stdout': symbols.stdout, 'stderr': symbols.stderr}
            if '__asan_report_' not in symbols.stdout:
                raise ValueError('Selected archive lacks Rust ASan report imports')
            report['scope'] = 'Actual pure Rust queue ASan and native C/C++ caller ASan/UBSan; precompiled Rust standard library uninstrumented. Native tokens and injected time; no PHP/reactor integration.'
        report['archive'] = str(archive)
        report['rustc'] = run(['rustc', '-Vv']).stdout
        report['cc'] = run(shlex.split(os.environ.get('CC', 'cc')) + ['--version']).stdout
        report['cxx'] = run(shlex.split(os.environ.get('CXX', 'c++')) + ['--version']).stdout
        with tempfile.TemporaryDirectory(prefix='swr-timer-kernel-') as temporary:
            directory = Path(temporary)
            # Compile the frozen header as C11 independently of the C++ executable.
            c_source = directory / 'layout.c'
            c_source.write_text('''#include "swoole_rs_timer.h"
_Static_assert(sizeof(void*) == 8, "64-bit supported hosts");
_Static_assert(sizeof(swr_v1_timer_view) == 56, "view size");
_Static_assert(offsetof(swr_v1_timer_view, token) == 48, "token offset");
_Static_assert(offsetof(swr_v1_timer_view, removed) == 40, "removed offset");
_Static_assert(sizeof(swr_v1_timer_stats) == 32, "stats size");
_Static_assert(_Generic(((swr_v1_timer_view*)0)->id, int64_t: 1, default: 0), "signed ID");
int timer_layout(void) { return SWR_TIMER_OK; }
''')
            run(shlex.split(os.environ.get('CC', 'cc')) + ['-std=c11', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'native/include'), '-c', str(c_source), '-o', str(directory / 'layout.o')])
            binary = directory / 'kernel'
            command = shlex.split(os.environ.get('CXX', 'c++')) + ['-std=c++17', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'native/include'), str(Path(__file__).with_suffix('.cc')), str(archive)]
            if args.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            command += ['-lc', '-lm']
            if sys.platform.startswith('linux'):
                command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            run(command + ['-o', str(binary)])
            result = run([str(binary)], timeout=15)
            report['observations'] = json.loads(result.stdout)
            report['passed'] = report['observations']['topics_passed'] == 13
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'observations': report.get('observations'),
                      'error': report.get('error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
