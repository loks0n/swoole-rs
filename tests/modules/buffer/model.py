#!/usr/bin/env python3
"""Seeded queue model versus the immutable archive and allocation-failure fixture."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from staging import apply_module_patch
from tools.harness import run_compiler

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    model_started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--build-manifest', type=Path, default=ROOT / 'target/hybrid/rust-buffer-websocket/build-manifest.json')
    parser.add_argument('--archive', type=Path, help='Check a private native candidate without claiming an extension build')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/buffer-model.json'))
    args = parser.parse_args()
    manifest = None if args.archive else json.loads(args.build_manifest.read_text())
    header = ROOT / 'native/include/swoole_rs_buffer.h'
    if manifest:
        if manifest['inputs']['upstream_commit'] != PIN or not manifest['migrated_feature_bits'] & 2:
            parser.error('Selected manifest must enable the buffer at the pinned upstream commit')
        prefix = next(a.partition('=')[2] for a in manifest['configure'] if a.startswith('--with-swoole-rs='))
        archive = (Path(prefix) / 'lib/libswoole_rs_ffi.a').resolve(strict=True)
        if sha(archive) != manifest['inputs']['rust_archive_sha256']:
            parser.error('Selected archive hash differs from its build manifest')
        if sha(header) != manifest['inputs']['headers_sha256'][str(header.relative_to(ROOT))]:
            parser.error('Current ABI header differs from the selected build')
    else:
        archive = args.archive.resolve(strict=True)
    local = Path(__file__).resolve().parent
    patches = [ROOT / 'migration/patches/buffer/0001-buffer-header.patch', ROOT / 'migration/patches/buffer/0002-buffer-body.patch']
    recorded = {p['path']: p['sha256'] for p in manifest['inputs']['patches']} if manifest else {}
    for patch in patches:
        if manifest and sha(patch) != recorded[str(patch.relative_to(ROOT))]:
            parser.error('Current facade patch differs from selected build: ' + str(patch))
    rust_source = ROOT / 'crates/buffer/src/lib.rs'
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'upstream_commit': PIN, 'host': platform.platform(), 'archive': str(archive),
              'production_rust_source_sha256': sha(rust_source),
              'sanitized': args.sanitize,
              'compiler': subprocess.check_output(shlex.split(os.environ.get('CXX', 'c++')) + ['--version'], text=True),
              'rustc': subprocess.check_output(['rustc', '--version'], text=True).strip(),
              'engines': {},
              'scope': 'Independent reference queue compares the real C ABI; real selected C++ facade checks offsets and callbacks. Exact published archive runs normally. Separate fixture recompiles unchanged production Rust source with a test-only one-shot failing GlobalAlloc, replaying each baseline allocation ordinal. No product allocator/ABI is modified.',
              'limitations': 'Fixed reproducible seeds, bounded byte lengths and one owning thread. ABI consumer offsets are external; facade offsets checked separately. No socket/process/fork workload. Sanitizers instrument C++ source/caller, not Rust instructions. Fixture source matches current production source hash; fixture binary is distinct from the published archive.'}
    with tempfile.TemporaryDirectory(prefix='swr-buffer-model-') as directory:
        tree = Path(directory)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/core/buffer.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
            for member in bundle:
                if member.isfile():
                    destination = tree / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(bundle.extractfile(member).read())
        report['patch_application'] = [apply_module_patch(tree, patch) for patch in patches]
        dependency_command = ['cargo', 'build', '-p', 'swoole-rs-buffer', '--release', '--offline', '--locked', '--message-format=json']
        dependency = run_isolated(dependency_command, timeout=60)
        report['fixture_dependency_build'] = {'command': dependency_command, 'returncode': dependency.returncode,
                                               'stdout': dependency.stdout, 'stderr': dependency.stderr}
        if dependency.returncode:
            write_report(args.output, report); print(dependency.stderr, file=sys.stderr); return 1
        artifacts = [json.loads(line) for line in dependency.stdout.splitlines() if line.startswith('{')]
        libraries = {row['target']['name']: Path(name) for row in artifacts
                     if row.get('reason') == 'compiler-artifact' and row['target']['name'] != 'swoole_rs_buffer'
                     for name in row['filenames'] if name.endswith('.rlib')}
        fixture = tree / 'libbuffer_model.a'
        rust_command = ['rustc', '--edition=2024', '--crate-type=staticlib', '--crate-name=swr_buffer_model',
                        '-C', 'opt-level=3',
                        *[arg for name, path in sorted(libraries.items()) for arg in ['--extern', name + '=' + str(path)]],
                        str(local / 'model_allocator.rs'), '-o', str(fixture)]
        report['fixture_compile_command'] = rust_command
        # The shared compiler cache does not yet hash --extern rlib contents.
        # Compile this small allocator fixture rather than reuse a stale binary.
        compiled = run_compiler(rust_command, timeout=60)
        report['fixture_compile'] = compiled
        if compiled['returncode']:
            write_report(args.output, report); print(compiled['stderr'], file=sys.stderr); return 1
        if sha(rust_source) != report['production_rust_source_sha256']:
            raise RuntimeError('Production Rust source changed during fixture compilation')
        for name, library in [('published', archive), ('allocation_fixture', fixture)]:
            binary = tree / name
            command = shlex.split(os.environ.get('CXX', 'c++')) + ['-std=c++17', '-O1', '-g', '-DSWOOLE_RS_BUFFER',
                '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/buffer'),
                str(tree / 'src/core/buffer.cc'), str(local / 'model.cc'), str(library), '-lc', '-lm']
            if name == 'allocation_fixture': command += ['-DMODEL_FAILURES']
            if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            if args.sanitize: command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
            command += ['-o', str(binary)]
            compiled = run_compiler(command, timeout=60)
            row = {'compile_command': command, 'compile': compiled}
            report['engines'][name] = row
            if compiled['returncode']:
                write_report(args.output, report); print(compiled['stderr'], file=sys.stderr); return 1
            started = time.monotonic()
            result = run_isolated([str(binary)], timeout=90)
            row['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                          'seconds': round(time.monotonic() - started, 4)}
            if result.returncode:
                write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
            row['outcome'] = json.loads(result.stdout)
            print(name + ': ' + result.stdout.strip())
        report['passed'] = True
        report['seconds'] = round(time.monotonic() - model_started, 4)
        write_report(args.output, report)
        print('Report: ' + args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
