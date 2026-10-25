#!/usr/bin/env python3
"""Build real Rust + applied overlay against checksum-pinned original C++.

No PHP/build alias/shared target is touched. Correctness checks, not benchmarks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tarfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def positive_benchmark_arguments(encode_only):
    prefix = 'encode-' if encode_only else ''
    return '--check-' + prefix + 'positive-benchmark', '--' + prefix + 'positive-benchmark'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/base64/differential.json')
    parser.add_argument('--encode-positive-only', action='store_true', help='Partial defined sequential encoding profile; no decoder/fault/thread/fork execution')
    parser.add_argument('--decode-positive-only', action='store_true', help='Partial canonical sequential decoding profile; no malformed/fault/thread/fork execution')
    parser.add_argument('--prepare-positive-benchmark', action='store_true', help='Preserve canonical-only optimized artifacts and perform untimed checksum preflight; requires a positive profile')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-sanitize', action='store_true',
                        help='Instrument Rust with ASan too; requires --sanitize and a private build')
    parser.add_argument('--archive', type=Path, help='Use the exact published hybrid Rust static archive instead of compiling a private crate')
    args = parser.parse_args()
    if args.rust_sanitize and (not args.sanitize or args.archive):
        parser.error('--rust-sanitize requires --sanitize and a private Rust build')
    if args.output.exists() or args.output.resolve().with_suffix('.bin').exists():
        parser.error('Refusing to overwrite an existing receipt/artifact')
    if args.encode_positive_only and args.decode_positive_only:
        parser.error('Choose one positive profile')
    positive_only = args.encode_positive_only or args.decode_positive_only
    if args.prepare_positive_benchmark and (not positive_only or args.sanitize):
        parser.error('Canonical preparation requires an unsanitized positive-only profile')
    for suffix in ['.a', '.sources.tar.gz']:
        if args.output.resolve().with_suffix('.bin' + suffix).exists():
            parser.error('Refusing existing immutable prepared inputs')
    rust_flags = ['-Zsanitizer=address'] if args.rust_sanitize else []
    rust_env = dict(os.environ, RUSTC_BOOTSTRAP='1') if args.rust_sanitize else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': PIN,
              'encode_positive_only': args.encode_positive_only, 'decode_positive_only': args.decode_positive_only, 'full_gate_passed': False, 'minimum_free_bytes': 4294967296,
              'sanitize': args.sanitize, 'rust_sanitized': args.rust_sanitize, 'rust_std_sanitized': False, 'passed': False, 'commands': []}

    def run(command, expect_failure=False, **kwargs):
        if positive_only:
            for path in [ROOT, Path(tempfile.gettempdir()), args.output.resolve().parent]:
                if shutil.disk_usage(path).free < report['minimum_free_bytes']:
                    report['blocked'] = str(path)
                    raise RuntimeError('Unchanged 4GiB guard')
        try:
            result = run_isolated([str(s) for s in command], timeout=60, **kwargs)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            report['commands'].append({'command': [str(s) for s in command], 'returncode': None,
                                       'timed_out': True, 'timeout_seconds': 60,
                                       'stdout': decoded(error.stdout), 'stderr': decoded(error.stderr)})
            raise
        report['commands'].append({'command': [str(s) for s in command], 'returncode': result.returncode,
                                   'expected_failure': expect_failure, 'stdout': result.stdout, 'stderr': result.stderr})
        if expect_failure:
            assert result.returncode != 0
        else:
            result.check_returncode()
        return result.stdout

    try:
        # Scratch is outside all Git worktrees. Sources come from pinned Git
        # objects, never from potentially modified working-tree source files.
        with tempfile.TemporaryDirectory(prefix='swoole-base64-') as temporary:
            scratch = Path(temporary)
            run(['git', 'init', '-q', scratch])
            for name in ['src/core/base64.cc', 'include/swoole_base64.h', 'core-tests/src/protocol/base64.cpp']:
                path = scratch / name
                path.parent.mkdir(parents=True, exist_ok=True)
                contents = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:{name}'], timeout=30)
                path.write_bytes(contents)
            original = scratch / 'original.cc'
            original.write_bytes((scratch / 'src/core/base64.cc').read_bytes())
            manifest = json.loads((ROOT / 'migration/patches/base64/manifest.json').read_text())
            assert manifest['upstream_commit'] == PIN
            for entry in manifest['patches']:
                patch = ROOT / 'migration/patches/base64' / entry['path']
                assert sha(patch) == entry['sha256']
                assert entry['upstream_paths'] == ['src/core/base64.cc']
                run(['git', '-C', scratch, 'apply', '--check', patch])
                run(['git', '-C', scratch, 'apply', patch])
            applied = scratch / 'src/core/base64.cc'
            assert applied.read_bytes() == (ROOT / 'native/base64/base64.cc').read_bytes()
            run(['rustc', '--edition=2024', *rust_flags, '--test',
                 ROOT / 'crates/base64/src/lib.rs', '-o', scratch / 'unit'], env=rust_env)
            if positive_only:
                tests = ['tests::encode_blocks_tails_and_canaries_match_bitstream_oracle'] if args.encode_positive_only else ['tests::classification_matches_alphabet_for_every_byte', 'tests::canonical_decode_preserves_full_output_and_canaries']
                for test in tests:
                    run([scratch / 'unit', '--exact', test])
            else:
                run([scratch / 'unit'])
            archive = args.archive.resolve(strict=True) if args.archive else scratch / 'libbase64.a'
            report['archive_origin'] = {'kind': 'published' if args.archive else 'private', 'path': str(archive)}
            if not args.archive:
                run(['rustc', '--edition=2024', *rust_flags, '--crate-name=swoole_rs_base64', '--crate-type=staticlib',
                     '-C', 'opt-level=3', '-C', 'panic=abort', ROOT / 'crates/base64/src/lib.rs', '-o', archive], env=rust_env)
            # Compile the unmodified original upstream core assertions with a
            # tiny deterministic fixture shim, rather than editing assertions.
            (scratch / 'test_core.h').write_text('''#pragma once
#include <cassert>
#include <cstddef>
#include <string>
using uchar = unsigned char;
#define TEST(suite, name) void original_##suite##_##name()
#define ASSERT_GT(a, b) assert((a) > (b))
#define ASSERT_EQ(a, b) assert((a) == (b))
inline size_t swoole_random_bytes(char *out, size_t n) {
    for (size_t i = 0; i < n; ++i) out[i] = static_cast<char>(i * 37 + 19);
    return n;
}
''')
            flags = ['-std=c++17', '-O3', '-g', '-I', scratch / 'include', '-I', ROOT / 'native/include', '-I', scratch]
            if args.sanitize:
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            oracle = scratch / 'oracle.o'
            run([os.environ.get('CXX', 'c++'), *flags, '-Dswoole=oracle', '-c', original, '-o', oracle])
            run([os.environ.get('CXX', 'c++'), *flags, '-c', applied, '-o', scratch / 'missing-flag.o'], expect_failure=True)
            assert 'Base64 overlay requires --enable-swoole-rs-base64' in report['commands'][-1]['stderr']
            report['negative_flag_gate'] = 'passed'
            (scratch / 'config.h').write_text('#define SWOOLE_RS_BASE64 1\n')
            run([os.environ.get('CXX', 'c++'), *flags, '-DHAVE_CONFIG_H', '-c', applied, '-o', scratch / 'configured.o'])
            report['config_header_gate'] = 'passed'
            (scratch / 'config.h').write_text('/* Feature deliberately omitted. */\n')
            run([os.environ.get('CXX', 'c++'), *flags, '-DHAVE_CONFIG_H', '-c', applied, '-o', scratch / 'unconfigured.o'], expect_failure=True)
            assert 'Base64 overlay requires --enable-swoole-rs-base64' in report['commands'][-1]['stderr']
            report['negative_config_header_gate'] = 'passed'
            binary = scratch / 'differential'
            libraries = ['-ldl', '-lpthread', '-lm'] if sys.platform.startswith('linux') else []
            run([os.environ.get('CXX', 'c++'), *flags, '-pthread', '-DSWOOLE_RS_BASE64=1', ROOT / 'tests/modules/base64/differential.cc', applied,
                 scratch / 'core-tests/src/protocol/base64.cpp', oracle, archive, *libraries, '-o', binary])
            symbols = run(['nm', '-g', binary])
            report['commands'][-1]['stdout'] = '\n'.join(s for s in symbols.splitlines() if 'swr_v1_base64_' in s)
            for symbol in ['swr_v1_base64_encode', 'swr_v1_base64_decode']:
                assert any(symbol in line and ' T ' in line for line in symbols.splitlines())
            profile = '--encode-positive' if args.encode_positive_only else '--decode-positive'
            report['result'] = json.loads(run([binary, profile] if positive_only else [binary]))
            if positive_only:
                report['benchmark_preflight'] = {'unrun': True, 'reason': 'Positive-only partial profile; no malformed input or measurement execution'}
                report['passed'] = report['result']['passed']
            else:
                report['benchmark_preflight'] = json.loads(run([binary, '--check-benchmark']))
                report['passed'] = report['result']['passed'] and report['benchmark_preflight']['preflight_passed']
            if args.prepare_positive_benchmark:
                report['benchmark_preflight'] = json.loads(run([binary, positive_benchmark_arguments(args.encode_positive_only)[0]]))
                assert report['benchmark_preflight']['preflight_passed'] and not report['benchmark_preflight']['timed']
            # Persist the validated executable so a later benchmark need not compile.
            artifact = args.output.resolve().with_suffix('.bin')
            shutil.copy2(binary, artifact)
            assert sha(artifact) == sha(binary)
            report['binary'] = str(artifact)
            if args.prepare_positive_benchmark:
                saved_archive = Path(str(artifact) + '.a')
                sources = Path(str(artifact) + '.sources.tar.gz')
                shutil.copy2(archive, saved_archive)
                with tarfile.open(sources, 'w:gz') as bundle:
                    for path in [original, applied, scratch / 'include/swoole_base64.h', scratch / 'core-tests/src/protocol/base64.cpp', scratch / 'test_core.h']:
                        bundle.add(path, arcname='native/' + str(path.relative_to(scratch)))
                    for path in [ROOT / 'crates/base64/src/lib.rs', ROOT / 'crates/base64/Cargo.toml', ROOT / 'crates/ffi/Cargo.toml', ROOT / 'crates/ffi/src/lib.rs', ROOT / 'Cargo.toml', ROOT / 'Cargo.lock', ROOT / 'native/include/swoole_rs_base64.h', Path(__file__), ROOT / 'tests/modules/base64/differential.cc']:
                        bundle.add(path, arcname='working-inputs/' + str(path.relative_to(ROOT)))
                report['prepared_inputs'] = {'archive': str(saved_archive), 'sources': str(sources), 'measurement_command': [str(artifact), positive_benchmark_arguments(args.encode_positive_only)[1]]}

    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'result': report.get('result'), 'report': str(args.output)}))


if __name__ == '__main__':
    main()
