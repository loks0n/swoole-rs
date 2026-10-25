#!/usr/bin/env python3
"""Check native upload resource boundaries in actual wrapper callbacks with real Rust state."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import overlay

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated, write_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['stream', 'map-registration', 'success', 'write', 'short-write'], default='stream')
    parser.add_argument('--fail-at', type=int, default=1, help='Native C++ allocation ordinal after successful fdopen')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--core-root', type=Path, required=True)
    parser.add_argument('--openssl-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    overlay.SOURCE = args.source
    tree = args.core_root.resolve() / 'core-rust'
    library = (tree / ('lib/libswoole.dylib' if sys.platform == 'darwin' else 'lib/libswoole.so')).resolve()
    generated = overlay.generated()['src/wrapper/http.cc']
    report = {'scope': __doc__, 'scenario': args.scenario, 'fail_at': args.fail_at, 'platform': sys.platform, 'upstream_pin': overlay.PIN,
              'rust_library': str(library), 'rust_library_sha256': sha(library), 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-fdopen-') as temporary:
        directory = Path(temporary)
        (directory / 'candidate-http.inc').write_text(generated)
        binary = directory / 'witness'
        command = ['c++', '-std=c++14', '-O2', '-UNDEBUG', '-DHAVE_CONFIG_H', '-DSWOOLE_RS_WRAPPERS',
                   '-I' + str(directory), '-I' + str(tree), '-I' + str(tree / 'include'),
                   '-I' + str(tree / 'thirdparty/llhttp'), '-I' + str(ROOT / 'native/wrappers'),
                   str(Path(__file__).with_suffix('.cc')), '-L' + str(tree / 'lib'),
                   '-Wl,-rpath,' + str(tree / 'lib'), '-lswoole', '-lpthread', '-o', str(binary)]
        if args.openssl_root:
            command[1:1] = ['-I' + str(args.openssl_root / 'include'), '-L' + str(args.openssl_root / 'lib')]
        if sys.platform == 'linux': command.append('-ldl')
        result = run_isolated(command, timeout=90)
        report.update(compile=command, compile_exit=result.returncode, compile_stderr=result.stderr)
        if not result.returncode:
            result = run_isolated([str(binary), args.scenario, str(args.fail_at)], timeout=30)
            report.update(exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
            try:
                observations = json.loads(result.stdout.strip().splitlines()[-1])
                actual = Path(observations['rust_library']).resolve()
                report.update(observations=observations, loaded_library_verified=actual == library and sha(actual) == report['rust_library_sha256'])
                report['passed'] = result.returncode == 0 and observations['passed'] and report['loaded_library_verified']
            except (ValueError, KeyError, IndexError) as error:
                report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'observations': report.get('observations'), 'error': report.get('error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
