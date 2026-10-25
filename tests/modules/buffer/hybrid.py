#!/usr/bin/env python3
"""Gate patched upstream facade against an existing feature-enabled Rust archive."""
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

from baseline import PIN
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from staging import apply_module_patch
from tools.harness import run_compiler


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    artifact = parser.add_mutually_exclusive_group(required=True)
    artifact.add_argument('--archive', type=Path)
    artifact.add_argument('--build-manifest', type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--patch', type=Path, action='append')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-asan', action='store_true', help='Supplied archive was separately compiled with Rust address sanitizer')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/buffer-hybrid.json'))
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    manifest = None
    if args.build_manifest:
        manifest = json.loads(args.build_manifest.read_text())
        if 'buffer' not in manifest['inputs']['modules']:
            parser.error('Build manifest does not enable buffer')
        prefix = next(value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-swoole-rs='))
        archive = Path(prefix) / 'lib/libswoole_rs_ffi.a'
    else:
        archive = args.archive
    archive = archive.resolve(strict=True)
    if args.rust_asan:
        if not args.sanitize:
            parser.error('Rust ASan archive requires the native sanitizer runtime')
        symbols = subprocess.run(['nm', '-u', str(archive)], capture_output=True, text=True)
        if '__asan_report_' not in symbols.stdout:
            parser.error('Selected archive lacks Rust ASan report imports')
    if manifest and sha(archive) != manifest['inputs']['rust_archive_sha256']:
        parser.error('Build archive hash does not match manifest')
    patches = args.patch or [ROOT / 'migration/patches/buffer/0001-buffer-header.patch',
                             ROOT / 'migration/patches/buffer/0002-buffer-body.patch']
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'upstream_commit': PIN, 'host': platform.platform(), 'archive': str(archive),
              'patches': [str(path) for path in patches],
              'rust_asan_declared': args.rust_asan,
              'sanitizer_scope': ('C++ source/facade/caller ASan+UBSan; supplied Rust archive separately ASan-instrumented'
                                  if args.rust_asan else 'C++ source/facade/caller ASan+UBSan; Rust archive not instrumented') if args.sanitize else 'none'}
    with tempfile.TemporaryDirectory(prefix='swr-buffer-hybrid-') as temporary:
        tree = Path(temporary)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/core/buffer.cc', 'src/core/string.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
            for member in bundle:
                if member.isfile():
                    destination = tree / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(bundle.extractfile(member).read())
        original_test = tree / 'core-tests/src/memory/buffer.cpp'
        original_test.parent.mkdir(parents=True)
        original_test.write_bytes(subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:core-tests/src/memory/buffer.cpp']))
        report['patch_application'] = [apply_module_patch(tree, patch, allow_override=bool(args.patch)) for patch in patches]
        binary = tree / 'hybrid'
        command = shlex.split(os.environ.get('CXX', 'c++')) + [
            '-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections', '-DSWOOLE_RS_BUFFER',
            '-I' + str(local), '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/buffer'),
            str(tree / 'src/core/buffer.cc'), str(tree / 'src/core/string.cc'), str(original_test),
            str(local / 'hybrid.cc'), str(archive),
            '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lc', '-lm',
        ]
        command += ['-Dswr_v1_buffer_' + name + '=swr_test_buffer_' + name
                    for name in ['append', 'stats', 'front', 'pop', 'front_plan', 'advance']]
        if sys.platform == 'linux':
            command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        if args.sanitize:
            command.append('-fsanitize=address,undefined')
        command += ['-o', str(binary)]
        report['compile_command'] = command
        compiled = run_compiler(command, timeout=45)
        report['compile'] = compiled
        if compiled['returncode']:
            write_report(args.output, report)
            print(compiled['stderr'], file=sys.stderr)
            return 1
        result = run_isolated([str(binary)], timeout=20)
        report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode == 0:
            report['outcome'] = json.loads(result.stdout)
        report['passed'] = result.returncode == 0
        write_report(args.output, report)
        print(f'Hybrid buffer gate passed={report["passed"]}; report={args.output}')
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
