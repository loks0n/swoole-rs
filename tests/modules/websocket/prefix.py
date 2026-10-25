#!/usr/bin/env python3
"""Compare header prefixes against the actual unchanged pinned C++ parser."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.harness import run_compiler

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--build-manifest', type=Path, default=ROOT / 'target/hybrid/rust-buffer-websocket/build-manifest.json')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-prefix.json'))
    parser.add_argument('--sanitize', action='store_true', help='C++ source/caller ASan+UBSan; Rust archive not instrumented')
    args = parser.parse_args()
    manifest = json.loads(args.build_manifest.read_text())
    if manifest['inputs']['upstream_commit'] != PIN or not manifest['migrated_feature_bits'] & 1:
        parser.error('Selected build must enable the WebSocket kernel at the pinned commit')
    prefix = next(value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-swoole-rs='))
    archive = (Path(prefix) / 'lib/libswoole_rs_ffi.a').resolve(strict=True)
    if sha(archive) != manifest['inputs']['rust_archive_sha256']:
        parser.error('Selected archive checksum differs from its build manifest')
    header = ROOT / 'native/include/swoole_rs_websocket.h'
    if sha(header) != manifest['inputs']['headers_sha256'][str(header.relative_to(ROOT))]:
        parser.error('Current ABI header differs from the selected build')
    local = Path(__file__).resolve().parent
    report = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'upstream_commit': PIN, 'host': platform.platform(), 'archive': str(archive),
              'sanitizer_scope': 'C++ source/caller ASan+UBSan; Rust archive not instrumented' if args.sanitize else 'none',
              'scope': 'Actual pinned C++ get_package_length versus Rust for all valid header prefixes. C++ extended integer loads use aligned input; identical Rust input covers all eight byte alignments. Signed overflow is Rust-only, never executed in the C++ oracle.'}
    with tempfile.TemporaryDirectory(prefix='swr-websocket-prefix-') as directory:
        tree = Path(directory)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN,
                                        'include', 'thirdparty', 'src/protocol/websocket.cc', 'src/protocol/base.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as bundle:
            for member in bundle:
                if member.isfile():
                    destination = tree / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(bundle.extractfile(member).read())
        binary = tree / 'prefix'
        includes = shlex.split(os.environ.get('CPPFLAGS', ''))
        openssl = next((value.partition('=')[2] for value in manifest['configure'] if value.startswith('--with-openssl-dir=')), None)
        if openssl:
            includes += ['-I' + str(Path(openssl) / 'include')]
        command = shlex.split(os.environ.get('CXX', 'c++')) + includes + [
            '-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections',
            '-I' + str(tree / 'include'), '-I' + str(tree / 'thirdparty'), '-I' + str(ROOT / 'native/include'),
            str(tree / 'src/protocol/websocket.cc'), str(tree / 'src/protocol/base.cc'), str(local / 'prefix.cc'), str(archive),
            '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lc', '-lm']
        if sys.platform.startswith('linux'):
            command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        command += ['-o', str(binary)]
        report['compile_command'] = command
        compiled = run_compiler(command, timeout=60)
        report['compile'] = compiled
        if compiled['returncode']:
            write_report(args.output, report)
            print(compiled['stderr'], file=sys.stderr)
            return 1
        result = run_isolated([str(binary)], timeout=15)
        report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        report['passed'] = result.returncode == 0
        if result.returncode == 0:
            report['outcome'] = json.loads(result.stdout)
        write_report(args.output, report)
        print(result.stdout if result.returncode == 0 else result.stderr, end='')
        print(f'Report: {args.output}')
        return int(result.returncode != 0)


if __name__ == '__main__':
    sys.exit(main())
