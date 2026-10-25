#!/usr/bin/env python3
"""Compile exact pinned C++ and patched adapter against Rust; never edit source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
from tools.build_hybrid import apply_patch_verified
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/crc32.json')
    parser.add_argument('--positive-only', action='store_true', help='Only defined sequential bytes/ordinary oracle cases; no defensive ranges, threads or fork; partial profile')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-sanitize', action='store_true',
                        help='Instrument the Rust crate with ASan too; requires --sanitize and clang++')
    parser.add_argument('--archive', type=Path, help='Link this exact selected hybrid Rust archive')
    parser.add_argument('--prepare-benchmark', type=Path,
                        help='After correctness, compile an optimized benchmark here; do not time it')
    args = parser.parse_args()
    if args.rust_sanitize and (not args.sanitize or args.archive):
        parser.error('--rust-sanitize requires --sanitize and a private Rust build')
    if args.output.exists():
        parser.error('Refusing to overwrite an existing receipt')
    if args.prepare_benchmark:
        for path in [args.prepare_benchmark, Path(str(args.prepare_benchmark) + '.a'), Path(str(args.prepare_benchmark) + '.sources.tar.gz')]:
            if path.exists():
                parser.error('Refusing existing immutable artifact: ' + str(path))
    rust_flags = ['-Zsanitizer=address'] if args.rust_sanitize else []
    rust_env = dict(os.environ, RUSTC_BOOTSTRAP='1') if args.rust_sanitize else None
    if args.sanitize and args.prepare_benchmark:
        parser.error('Performance preparation requires an unsanitized build')
    report = {'passed': False, 'platform': platform.platform(), 'upstream_commit': PIN,
              'positive_only': args.positive_only, 'full_gate_passed': False, 'minimum_free_bytes': 4294967296,
              'scope': 'Defined sequential CRC bytes and original CRC assertion only; full default probe unrun' if args.positive_only else 'Historical full default CRC probe; independent project completion gates remain',
              'sanitized_native': args.sanitize, 'rust_sanitized': args.rust_sanitize, 'rust_std_sanitized': False, 'commands': []}

    def run(command, cwd, timeout=60, env=None, expect_failure=False):
        argv = [str(arg) for arg in command]
        if args.positive_only:
            for path in [ROOT, scratch, args.output.resolve().parent]:
                while not path.exists():
                    path = path.parent
                free = shutil.disk_usage(path).free
                if free < report['minimum_free_bytes']:
                    report['blocked'] = {'path': str(path), 'free_bytes': free, 'before': argv}
                    raise RuntimeError('Unchanged4GiBguard')
        try:
            result = run_isolated(argv, cwd=cwd, timeout=timeout, env=env)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            report['commands'].append({'argv': argv, 'exit_code': None,
                                       'timed_out': True, 'timeout_seconds': timeout,
                                       'stdout': decoded(error.stdout), 'stderr': decoded(error.stderr)})
            raise
        report['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                   'timeout_seconds': timeout, 'expected_failure': expect_failure,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        if expect_failure:
            assert result.returncode != 0
        else:
            result.check_returncode()
        return result.stdout

    try:
        with tempfile.TemporaryDirectory(prefix='swoole-crc32-') as temporary:
            scratch = Path(temporary)  # Outside all Git worktrees; no mutable oracle checkout.
            original = subprocess.check_output(['git', '-C', str(args.source), 'show',
                                                f'{PIN}:src/core/crc32.cc'], timeout=15)
            header = subprocess.check_output(['git', '-C', str(args.source), 'show',
                                             f'{PIN}:include/swoole_hash.h'], text=True, timeout=15)
            assert 'uint32_t swoole_crc32(const char *data, size_t size);' in header
            core_test = subprocess.check_output(['git', '-C', str(args.source), 'show',
                                                f'{PIN}:core-tests/src/core/hash.cpp'], text=True, timeout=15)
            # Extract the original CRC32 test and its shared input verbatim, with
            # a minimal assertion shim; unrelated hash functions are out of scope.
            data = re.search(r'^static const char \*data = .*;$', core_test, re.M).group()
            test = re.search(r'TEST\(hash, crc32\) \{[^}]+\}', core_test).group()
            (scratch / 'core-test.cc').write_text(
                '#include <cassert>\n#include <cstring>\n#include "swoole.h"\n'
                '#include "swoole_hash.h"\n#define TEST(a,b) void a##_##b()\n'
                '#define ASSERT_EQ(a,b) assert((a) == (b))\n' + data + '\n' + test + '\n')
            (scratch / 'swoole.h').write_text('#ifdef HAVE_CONFIG_H\n#include \"config.h\"\n#endif\n#include <cstddef>\n#include <cstdint>\n#define sw_unlikely(x) (x)\n')
            (scratch / 'swoole_hash.h').write_text('uint32_t swoole_crc32(const char *, size_t);\n')
            (scratch / 'original.cc').write_bytes(original)
            destination = scratch / 'src/core/crc32.cc'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(original)
            manifest = json.loads((ROOT / 'migration/patches/crc32/manifest.json').read_text())
            assert manifest['upstream_commit'] == PIN
            for entry in manifest['patches']:
                patch = ROOT / 'migration/patches/crc32' / entry['path']
                assert sha(patch.read_bytes()) == entry['sha256']
                assert entry['upstream_paths'] == ['src/core/crc32.cc']
                report.setdefault('patch_applications', []).append(apply_patch_verified(scratch, patch, entry['upstream_paths'], entry['sha256']))
            assert destination.read_bytes() == (ROOT / 'native/crc32/adapter.cc').read_bytes()
            rust = ROOT / 'crates/crc32/src/lib.rs'
            run(['rustc', '--edition=2024', *rust_flags, '--test', rust, '-o', scratch / 'unit'], ROOT, env=rust_env)
            if args.positive_only:
                for test in ['tests::standard_vectors', 'tests::exhaustive_two_byte_bitwise_oracle', 'tests::sliced_blocks_and_tails_match_bitwise_oracle']:
                    run([scratch / 'unit', '--exact', test], ROOT)
            else:
                run([scratch / 'unit'], ROOT)
            if args.archive:
                archive = args.archive.resolve(strict=True)
                report['archive_source'] = str(archive)
            else:
                archive = scratch / 'libcrc32.a'
                run(['rustc', '--edition=2024', *rust_flags, '--crate-type=staticlib', '-C', 'opt-level=3',
                     '-C', 'panic=abort', rust, '-o', archive], ROOT, env=rust_env)
                report['archive_source'] = 'standalone implementation compiled above'
            flags = ['-std=c++17', '-O2', '-g', '-I', scratch, '-I', ROOT / 'native/include']
            if args.positive_only:
                flags += ['-DSWR_CRC32_POSITIVE_ONLY']
            if args.sanitize:
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            compiler = os.environ.get('CXX', 'c++')
            run([compiler, *flags, '-Dswoole_crc32=upstream_crc32', '-c', scratch / 'original.cc',
                 '-o', scratch / 'original.o'], ROOT)
            run([compiler, *flags, '-c', destination, '-o', scratch / 'missing.o'], ROOT, expect_failure=True)
            assert 'CRC32 overlay requires --enable-swoole-rs-crc32' in report['commands'][-1]['stderr']
            (scratch / 'config.h').write_text('#define SWOOLE_RS_CRC32 1\n')
            run([compiler, *flags, '-DHAVE_CONFIG_H', '-c', destination, '-o', scratch / 'configured.o'], ROOT)
            (scratch / 'config.h').write_text('/* Feature deliberately omitted. */\n')
            run([compiler, *flags, '-DHAVE_CONFIG_H', '-c', destination, '-o', scratch / 'unconfigured.o'], ROOT, expect_failure=True)
            assert 'CRC32 overlay requires --enable-swoole-rs-crc32' in report['commands'][-1]['stderr']
            report['feature_guards'] = {'missing_define_rejected': True, 'configured_define_accepted': True, 'missing_config_define_rejected': True}
            run([compiler, *flags, '-DSWOOLE_RS_CRC32', destination,
                 ROOT / 'tests/modules/crc32/probe.cc', scratch / 'core-test.cc', scratch / 'original.o', archive,
                 '-pthread', '-o', scratch / 'probe'], ROOT)
            symbols = run(['nm', '-g', scratch / 'probe'], ROOT)
            assert 'swr_v1_crc32' in symbols
            report['commands'][-1]['stdout'] = '\n'.join(line for line in symbols.splitlines() if 'swr_v1_crc32' in line)
            report['results'] = json.loads(run([scratch / 'probe'], ROOT, timeout=30))
            if args.prepare_benchmark:
                benchmark_source = ROOT / 'tests/modules/crc32/benchmark.cc'
                # The upstream object above uses -O2. Recompile it at the same
                # optimization level as the adapter and driver before relinking.
                run([compiler, *flags, '-O3', '-Dswoole_crc32=upstream_crc32',
                     '-c', scratch / 'original.cc', '-o', scratch / 'original.o'], ROOT)
                run([compiler, *flags, '-O3', '-DSWOOLE_RS_CRC32', destination,
                     benchmark_source, scratch / 'original.o', archive,
                     '-pthread', '-o', scratch / 'benchmark'], ROOT)
                executable = args.prepare_benchmark.resolve()
                executable.parent.mkdir(parents=True, exist_ok=True)
                if executable.exists():
                    raise FileExistsError(f'Refusing to overwrite benchmark: {executable}')
                shutil.copy2(scratch / 'benchmark', executable)
                saved_archive = Path(str(executable) + '.a')
                source_bundle = Path(str(executable) + '.sources.tar.gz')
                shutil.copy2(archive, saved_archive)
                with tarfile.open(source_bundle, 'w:gz') as bundle:
                    for path in [scratch / 'original.cc', destination, scratch / 'swoole.h', scratch / 'swoole_hash.h', scratch / 'core-test.cc']:
                        bundle.add(path, arcname='native/' + str(path.relative_to(scratch)))
                    for path in [rust, benchmark_source, ROOT / 'native/include/swoole_rs_crc32.h', ROOT / 'native/crc32/adapter.cc', ROOT / 'migration/patches/crc32/manifest.json', ROOT / 'Cargo.toml', ROOT / 'Cargo.lock', ROOT / 'crates/ffi/Cargo.toml', ROOT / 'crates/crc32/Cargo.toml', Path(__file__)]:
                        bundle.add(path, arcname='working-inputs/' + str(path.relative_to(ROOT)))
                report['prepared_inputs'] = {'archive': str(saved_archive), 'sources': str(source_bundle)}
                report['benchmark'] = {'executable': str(executable),
                                       'sha256': sha(executable.read_bytes()),
                                       'measured': False}
                report['benchmark']['preflight'] = [json.loads(run(
                    [executable, 'rust', str(size), '1', 'check'], ROOT, timeout=30))
                    for size in (0, 1, 2, 3, 20, 28, 64, 128, 1024, 65536)]
                report['benchmark']['ipv6_loopback_preflight'] = json.loads(run(
                    [executable, 'rust', '28', '1', 'check', 'ipv6-loopback'], ROOT, timeout=30))
            report['passed'] = True
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'results': report['results'], 'report': str(args.output)}))


if __name__ == '__main__':
    main()
