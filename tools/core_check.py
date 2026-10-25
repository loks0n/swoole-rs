#!/usr/bin/env python3
"""Run a core differential against the exact verified hybrid archive."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT
from tools.build_hybrid import MODULES


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', choices=['base64', 'crc32', 'error'], required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--encode-positive-only', action='store_true', help='Base64 sequential defined encodes only; decoder and full gate remain unrun')
    parser.add_argument('--positive-only', action='store_true', help='CRC32 sequential defined bytes and original CRC assertion only')
    args = parser.parse_args()
    if args.encode_positive_only and args.module != 'base64' or args.positive_only and args.module != 'crc32':
        parser.error('Positive profile does not match selected module')
    manifest = json.loads(args.build_manifest.read_text())
    if args.module not in manifest['inputs']['modules'] or not manifest['migrated_feature_bits'] & MODULES[args.module][1]:
        parser.error('Selected build does not enable this module')
    prefix = next(value.split('=', 1)[1] for value in manifest['configure'] if value.startswith('--with-swoole-rs='))
    archive = (Path(prefix) / 'lib/libswoole_rs_ffi.a').resolve(strict=True)
    header = Path('native/include') / f'swoole_rs_{args.module}.h'
    if sha(archive) != manifest['inputs']['rust_archive_sha256'] or sha(ROOT / header) != manifest['inputs']['headers_sha256'][str(header)]:
        parser.error('Archive or current ABI header differs from selected build')
    for patch in manifest['inputs']['patches']:
        if patch['path'].startswith(f'migration/patches/{args.module}/') and sha(ROOT / patch['path']) != patch['sha256']:
            parser.error('Current overlay differs from selected build')
    runner = 'differential.py' if args.module == 'error' else 'check.py'
    return subprocess.run([sys.executable, str(ROOT / 'tests/modules' / args.module / runner),
                           '--source', str(ROOT / 'target/upstream/src'), '--archive', str(archive),
                           '--output', str(args.output), *(['--sanitize'] if args.sanitize else []),
                           *(['--encode-positive-only'] if args.encode_positive_only else []),
                           *(['--positive-only'] if args.positive_only else [])], cwd=ROOT).returncode


if __name__ == '__main__':
    sys.exit(main())
