#!/usr/bin/env python3
"""Compile pinned original/patched error.cc and compare through the actual Rust ABI."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import os
import signal
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/error-differential.json')
    parser.add_argument('--archive', type=Path, help='Use the exact published Cargo/FFI archive without recompiling Rust')
    parser.add_argument('--allocator-faults', action='store_true', help='Compile unchanged Rust with a test allocator and check actual native bad_alloc translation')
    parser.add_argument('--sanitize', action='store_true', help='Instrument the native oracle, adapter and driver with ASan/UBSan')
    parser.add_argument('--benchmark', action='store_true', help='Requires an explicit exclusive benchmark lease; seven matched optimized trials')
    parser.add_argument('--prepare-benchmark', type=Path, help='Retain a verified optimized executable without running timed trials')
    args = parser.parse_args()
    if args.allocator_faults and (args.archive or args.benchmark or args.prepare_benchmark):
        parser.error('Allocator-fault artifacts are test-only, never published archives or benchmarks')
    if (args.benchmark or args.prepare_benchmark) and args.sanitize:
        parser.error('Benchmarks require an optimized unsanitized build')
    if args.prepare_benchmark and args.prepare_benchmark.exists():
        parser.error('Benchmark destination must be new so prepared artifacts remain immutable')
    report = {'upstream_commit': PIN, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'native_sanitizers': args.sanitize, 'commands': [], 'sha256': {},
              'scope': 'Actual complete pinned error.cc and enum; only swoole.h dependency surface stubbed. '
                       'No PHP/extension/build activation or performance claim.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def run(command, cwd=None, expect_failure=False):
        # Bound every compiler/probe; terminate its whole private group on timeout/interruption.
        process = subprocess.Popen([str(x) for x in command], cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=60)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report['commands'].append({'argv': [str(x) for x in command],
                                       'returncode': process.returncode, 'interrupted': True,
                                       'stdout': stdout, 'stderr': stderr})
            raise
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        report['commands'].append({'argv': [str(x) for x in command], 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr, 'expected_failure': expect_failure})
        if bool(result.returncode) != expect_failure:
            raise RuntimeError(f'Command failed: {command}')
        return result.stdout

    def pinned(path):
        return run(['git', '-C', args.source.resolve(), 'show', f'{PIN}:{path}'])

    try:
        report['rustc'] = run(['rustc', '--version']).strip()
        report['cxx'] = run(['c++', '--version']).splitlines()[0]
        original = pinned('src/core/error.cc')
        header = pinned('include/swoole_error.h')
        cases = re.findall(r'case (SW_ERROR_\w+):', original)
        names = list(dict.fromkeys(re.findall(r'\bSW_ERROR_\w+\b', header)))
        assert len(cases) == 130 and len(cases) == len(set(cases))
        manifest = json.loads((ROOT / 'migration/patches/error/manifest.json').read_text())
        assert manifest['upstream_commit'] == PIN and len(manifest['patches']) == 1
        patch_entry = manifest['patches'][0]
        assert patch_entry['upstream_paths'] == ['src/core/error.cc']
        patch = ROOT / 'migration/patches/error' / patch_entry['path']
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == patch_entry['sha256']
        # The scratch source is deliberately outside every worktree, never the reference.
        with tempfile.TemporaryDirectory(prefix='swoole-error-') as temporary:
            work = Path(temporary)
            (work / 'src/core').mkdir(parents=True)
            (work / 'src/core/error.cc').write_text(original)
            (work / 'original.cc').write_text(original)
            (work / 'swoole_error.h').write_text(header)
            stub = '''#pragma once
#include <cstdio>
#include <cstring>
#include <exception>
#include "swoole_error.h"
const char *swoole_strerror(int);
void swoole_throw_error(int);
void swoole_ignore_error(int);
bool swoole_is_ignored_error(int);
void swoole_clear_last_error_msg();
const char *swoole_get_last_error_msg();
extern char sw_error[1024];
'''
            (work / 'swoole.h').write_text(stub)
            run(['git', 'apply', '--check', patch], work)
            run(['git', 'apply', patch], work)
            patched = (work / 'src/core/error.cc').read_text()
            assert 'switch (code)' not in patched and 'swr_v1_error_strerror(code, swr_system_error)' in patched
            assert patched.split('void swoole_throw_error')[1].split('void swoole_ignore_error')[0] == original.split('void swoole_throw_error')[1].split('void swoole_ignore_error')[0]
            assert patched.split('void swoole_clear_last_error_msg')[1] == original.split('void swoole_clear_last_error_msg')[1]
            shutil.copyfile(ROOT / 'native/include/swoole_rs_error.h', work / 'swoole_rs_error.h')
            shutil.copyfile(ROOT / 'native/error/swoole_rs_error_resolver.h', work / 'swoole_rs_error_resolver.h')
            shutil.copyfile(ROOT / 'native/error/swoole_rs_error_state.h', work / 'swoole_rs_error_state.h')
            rust = ROOT / 'crates/error/src/lib.rs'
            archive = args.archive.resolve() if args.archive else work / 'liberror.a'
            if args.archive:
                report['published_archive'] = str(archive)
                assert archive.is_file(), f'Missing published archive: {archive}'
            else:
                if args.allocator_faults:
                    wrapper = (ROOT / 'tests/modules/error/allocator.rs').read_text()
                    wrapper = wrapper.replace('/* ERROR_MODULE */', f'#[path = {json.dumps(str(rust))}] mod error;')
                    (work / 'allocator.rs').write_text(wrapper)
                    rust_input = work / 'allocator.rs'
                else:
                    rust_input = rust
                run(['rustc', '--edition=2024', '--crate-name', 'swoole_rs_error', '--crate-type', 'staticlib',
                     '-C', 'opt-level=3', '-C', 'panic=abort', rust_input, '-o', archive])
            rename = ['swoole_strerror', 'swoole_throw_error', 'swoole_ignore_error',
                      'swoole_is_ignored_error', 'swoole_clear_last_error_msg', 'swoole_get_last_error_msg']
            flags = ['-std=c++17', '-O2', '-I', work]
            if args.sanitize:
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            run(['c++', *flags, '-fsyntax-only', work / 'src/core/error.cc'], expect_failure=True)
            assert 'Error overlay requires --enable-swoole-rs-error' in report['commands'][-1]['stderr']
            run(['c++', *flags, '-Dswoole=reference_swoole',
                 *[f'-D{name}=reference_{name}' for name in rename], '-c', work / 'original.cc', '-o', work / 'original.o'])
            run(['c++', *flags, '-DSWOOLE_RS_ERROR', '-c', work / 'src/core/error.cc', '-o', work / 'patched.o'])
            if args.allocator_faults:
                run(['c++', *flags, ROOT / 'tests/modules/error/allocator.cc', work / 'patched.o',
                     archive, '-o', work / 'allocator-probe'])
                report['allocator_faults'] = json.loads(run([work / 'allocator-probe']))
                report['allocator_archive_scope'] = 'Unchanged production Rust with test-only failing global allocator; not a published PHP archive or Rust-ASan build'
            driver = (ROOT / 'tests/modules/error/driver.cc').read_text()
            driver = driver.replace('/* KNOWN_CASES */', ', '.join(cases))
            driver = driver.replace('/* ALL_ENUMS */', ', '.join(names))
            (work / 'driver.cc').write_text(driver)
            run(['c++', *flags, '-pthread', work / 'driver.cc', work / 'original.o', work / 'patched.o',
                 archive, '-o', work / 'probe'])
            symbols = run(['nm', '-g', work / 'probe'])
            assert re.search(r'\bT\s+_?swr_v1_error_message\b', symbols)
            report['commands'][-1]['stdout'] = 'swr_v1_error_message defined'
            report['result'] = json.loads(run([work / 'probe']))
            report['native_lines_removed'] = len(original.splitlines()) - len(patched.splitlines())
            if args.benchmark or args.prepare_benchmark:
                report['benchmark_workloads'] = ['all-known', 'hot', 'system', 'unknown']
                benchmark = (ROOT / 'tests/modules/error/benchmark.cc').read_text()
                (work / 'benchmark.cc').write_text(benchmark.replace('/* KNOWN_CASES */', ', '.join(cases)))
                run(['c++', *flags, '-pthread', work / 'benchmark.cc', work / 'original.o', work / 'patched.o',
                     archive, '-o', work / 'benchmark'])
                report['sha256']['benchmark'] = hashlib.sha256((work / 'benchmark').read_bytes()).hexdigest()
                state_source = ROOT / 'tests/modules/error/benchmark-state.cc'
                run(['c++', *flags, '-pthread', state_source, work / 'original.o', work / 'patched.o',
                     archive, '-o', work / 'state-benchmark'])
                report['state_preflight'] = json.loads(run([work / 'state-benchmark', '--check']))
                assert report['state_preflight']['timed'] is False and report['state_preflight']['errors'] == 0
                report['state_benchmark_workloads'] = [row['workload'] for row in report['state_preflight']['trials']]
                report['state_latency_preflight'] = json.loads(run([work / 'state-benchmark', '--check-latency']))
                assert report['state_latency_preflight']['timed'] is False
                assert report['state_latency_preflight']['latency_mode'] is True
                assert report['state_latency_preflight']['errors'] == 0
                assert [row['workload'] for row in report['state_latency_preflight']['trials']] == report['state_benchmark_workloads']
                for row in report['state_latency_preflight']['trials']:
                    assert row['upstream_batch_mean_ns_p50'] == 0
                    assert row['rust_batch_mean_ns_p50'] == 0
                report['sha256']['state-benchmark'] = hashlib.sha256((work / 'state-benchmark').read_bytes()).hexdigest()
                if args.prepare_benchmark:
                    destination = args.prepare_benchmark.resolve()
                    destination.mkdir(parents=True)
                    shutil.copy2(work / 'benchmark', destination / 'benchmark')
                    shutil.copy2(work / 'state-benchmark', destination / 'state-benchmark')
                    report['prepared_benchmark'] = str(destination / 'benchmark')
                    report['passed'] = True
                    (destination / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
                if args.benchmark:
                    report['benchmark'] = json.loads(run([work / 'benchmark']))
                    report['state_latency_benchmark'] = json.loads(run([work / 'state-benchmark', '--latency']))
            report['passed'] = True
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], **report['result'], 'report': str(args.output)}))


if __name__ == '__main__':
    main()
