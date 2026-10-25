#!/usr/bin/env python3
"""Compare actual pinned/patched HTTP2 core TUs; native Socket send is recorded.

No PHP, network, HPACK, or server/client lifetime parity is implied. Native
alignment checks are excluded because pinned inline codecs use unaligned casts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
from tools.build_upstream import COMMIT as PIN
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--include', action='append', default=[])
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    work = args.output.parent / (args.output.stem + '-artifacts')
    work.mkdir(parents=True, exist_ok=False)
    commands = []
    report = {'passed': False, 'upstream_commit': PIN, 'scope': 'actual core production translation unit; Socket::send recording double',
              'not_covered': ['PHP client/server production TUs and runtime', 'HPACK', 'reentrant stream/session lifetimes', 'performance'],
              'native_sanitizers': ['address', 'undefined except alignment'] if args.sanitize else [],
              'rust_sanitized': False, 'commands': commands,
              'module_header_sha256': digest(ROOT / 'native/http2/rust_http2.h')}

    def run(command, cwd=None):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        record = {'command': command, 'cwd': str(cwd or Path.cwd()), 'returncode': result.returncode,
                  'stdout': result.stdout, 'stderr': result.stderr}
        commands.append(record)
        (work / f'{len(commands):03d}.json').write_text(json.dumps(record, indent=2) + '\n')
        result.check_returncode()
        return result.stdout

    try:
        manifest = json.loads((ROOT / 'migration/patches/http2/manifest.json').read_text())
        if manifest['upstream_commit'] != PIN:
            raise ValueError('Overlay pin mismatch')
        patch = manifest['patches'][0]
        scratch = work / 'overlay'
        for name in patch['upstream_paths']:
            text = run(['git', 'show', f'{PIN}:{name}'], args.source)
            path = scratch / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        report['overlay'] = apply_patch_verified(scratch, ROOT / 'migration/patches/http2' / patch['path'],
                                                patch['upstream_paths'], patch['sha256'])
        report['patched_sources'] = {name: digest(scratch / name) for name in patch['upstream_paths']}
        original = work / 'original.cc'
        name = 'src/protocol/http2.cc'
        original.write_text(run(['git', 'show', f'{PIN}:{name}'], args.source))
        # Include headers must belong to this exact pinned checkout, not a moving build.
        if run(['git', 'rev-parse', 'HEAD'], args.source).strip() != PIN:
            raise ValueError('Public include source checkout is not pinned')
        if run(['git', 'status', '--porcelain', '--', 'include'], args.source).strip():
            raise ValueError('Pinned public headers have local changes')
        rust_sources = {str(path.relative_to(ROOT)): digest(path)
                        for path in sorted((ROOT / 'crates/http2/src').rglob('*.rs'))}
        report['rust_sources'] = rust_sources
        archive = args.archive.resolve() if args.archive else work / 'libhttp2.a'
        unit = work / 'policy-unit'
        run(['rustc', '--edition=2021', '--test', ROOT / 'crates/http2/src/lib.rs', '-o', unit])
        report['rust_unit_output'] = run([unit])
        if not args.archive:
            run(['rustc', '--edition=2021', '--crate-type', 'staticlib', '-C', 'opt-level=2', '-C', 'panic=abort',
                 ROOT / 'crates/http2/src/lib.rs', '-o', archive])
        report['archive'] = str(archive)
        report['archive_origin'] = 'provided' if args.archive else 'standalone selected Rust source'
        report['archive_sha256'] = digest(archive)
        compiler = os.environ.get('CXX', 'c++')
        base = [compiler, '-std=c++17', '-I', ROOT / 'native/http2', '-I', args.source / 'include']
        for include in args.include:
            base += ['-I', include]
        if args.sanitize:
            base += ['-fsanitize=address,undefined', '-fno-sanitize=alignment', '-fno-omit-frame-pointer', '-g']
        functions = ['put_default_setting', 'get_default_setting', 'pack_setting_frame', 'unpack_setting_data',
                     'get_frame_length', 'send_setting_frame', 'get_type', 'get_type_color']
        run(base + [f'-D{name}=original_{name}' for name in functions] + ['-c', original, '-o', work / 'original.o'])
        run(base + ['-DSW_USE_RUST_HTTP2', '-c', scratch / name, '-o', work / 'rust.o'])
        # Compile the disabled overlay too, proving the native fallback needs no Rust headers or archive.
        run(base + ['-c', scratch / name, '-o', work / 'disabled.o'])
        executable = work / 'core-calls'
        harness = ROOT / 'tests/modules/http2/core_calls.cpp'
        run(base + ['-DSW_USE_RUST_HTTP2', harness, work / 'original.o', work / 'rust.o', archive, '-o', executable])
        report['core_calls'] = json.loads(run([executable]))
        if digest(ROOT / 'native/http2/rust_http2.h') != report['module_header_sha256']:
            raise ValueError('Module header changed during checks')
        if rust_sources != {str(path.relative_to(ROOT)): digest(path)
                            for path in sorted((ROOT / 'crates/http2/src').rglob('*.rs'))}:
            raise ValueError('Rust module sources changed during checks')
        report['passed'] = report['core_calls']['passed']
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.output), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
