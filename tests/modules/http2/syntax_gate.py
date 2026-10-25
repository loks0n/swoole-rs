#!/usr/bin/env python3
"""Syntax-check all actual HTTP2 TUs with installed PHP header configuration.

This bounded configuration uses ENABLE_PHP_SWOOLE/php_config.h, not a configured
extension build unless --configured-headers provides a verified immutable SDK.
Unselected configuration variants and runtime behavior remain untested.
"""
import argparse
import io
import tarfile
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--php-config', default='php-config')
    parser.add_argument('--include', action='append', default=[])
    parser.add_argument('--configured-headers', type=Path, help='Immutable completed-build SDK with identity.json')
    args = parser.parse_args()
    core = json.loads(args.core_report.read_text())
    if not core['passed']:
        raise ValueError('Completed passing core receipt required')
    overlay = args.core_report.parent / (args.core_report.stem + '-artifacts') / 'overlay'
    work = args.output.parent / (args.output.stem + '-artifacts')
    work.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'scope': __doc__, 'upstream_commit': gate.PIN, 'commands': [], 'dependencies': []}
    includes = shlex.split(subprocess.check_output([args.php_config, '--includes'], text=True))
    report['php_version'] = subprocess.check_output([args.php_config, '--version'], text=True).strip()
    # Quoted config.h includes resolve beside php_swoole.h before -I paths.
    # Export tracked headers so a checkout's untracked build config cannot leak in.
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', gate.PIN], cwd=args.source, text=True).splitlines()
    names = [name for name in names if Path(name).suffix in {'.h', '.hpp', '.inc'}]
    archive = subprocess.check_output(['git', 'archive', '--format=tar', gate.PIN, '--', *names], cwd=args.source)
    private_headers = work / 'pinned-headers'
    with tarfile.open(fileobj=io.BytesIO(archive)) as files:
        for member in files:
            if not member.isfile():
                continue
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe header archive path')
            path = private_headers / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files.extractfile(member).read())
    header_identity = gate.digest(gate.ROOT / 'native/http2/rust_http2.h')
    if core.get('module_header_sha256') != header_identity:
        raise ValueError('Core receipt lacks matching module-header identity')
    sdk_files = {}
    if args.configured_headers:
        sdk = args.configured_headers.resolve()
        identity = json.loads((sdk / 'identity.json').read_text())
        sdk_files = {name: gate.digest(sdk / name) for name in identity['files']}
        if sdk_files != identity['files']:
            raise ValueError('Configured SDK identity mismatch')
        # Place the copied config beside copied php_swoole.h for quoted resolution.
        for name in sdk_files:
            if name == 'config.h' or name.startswith(('include/', 'thirdparty/')):
                destination = private_headers / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((sdk / name).read_bytes())
        report['configured_sdk'] = identity
    base = [os.environ.get('CXX', 'c++'), '-std=c++17', '-fsyntax-only', '-DENABLE_PHP_SWOOLE',
            '-I', str(gate.ROOT / 'native/http2')]
    if args.configured_headers:
        base += ['-DHAVE_CONFIG_H', '-I', str(sdk / 'rust-prefix/include')]
    for include in [private_headers, private_headers / 'include', private_headers / 'ext-src', private_headers / 'thirdparty', *args.include]:
        base += ['-I', str(include)]
    base += includes
    for name in core['patched_sources']:
        if gate.digest(overlay / name) != core['patched_sources'][name]:
            raise ValueError('Overlay changed after core receipt')
        for enabled in (False, True):
            dep = work / (Path(name).name + ('.rust.d' if enabled else '.native.d'))
            command = base + (['-DSW_USE_RUST_HTTP2'] if enabled else []) + ['-MD', '-MF', str(dep), str(overlay / name)]
            result = subprocess.run(command, capture_output=True, text=True)
            report['commands'].append({'command': command, 'returncode': result.returncode,
                                       'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode == 0:
                paths = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
                report['dependencies'] += [str(Path(path).resolve()) for path in paths]
    if args.configured_headers and any(gate.digest(sdk / name) != sha for name, sha in sdk_files.items()):
        raise ValueError('Configured SDK changed during checks')
    if gate.digest(gate.ROOT / 'native/http2/rust_http2.h') != header_identity:
        raise ValueError('Module header changed during checks')
    if any(str(args.source.resolve()) in path for path in report['dependencies']):
        raise ValueError('Compiler read a dependency from the source checkout')
    report['configuration_scope'] = 'private pinned tracked headers plus attested SDK overlay' if args.configured_headers else 'private pinned tracked headers plus installed PHP header configuration'
    report['passed'] = len(report['commands']) == 6 and all(item['returncode'] == 0 for item in report['commands'])
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
