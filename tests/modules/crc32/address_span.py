#!/usr/bin/env python3
"""Prove defined real native Address/CRC span semantics without changing callers.

Consumes a completed private native-core build, reads its frozen library/source,
and compiles only a tiny fixture plus checksum-pinned original CRC oracle.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--native-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'passed': False, 'scope': __doc__, 'commands': [], 'sanitized_native_library': False}

    def run(command):
        result = run_isolated(list(map(str, command)), timeout=30)
        report['commands'].append({'argv': list(map(str, command)), 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        result.check_returncode()
        return result.stdout

    try:
        native = json.loads(args.native_report.read_text())
        assert native['status'] == 'complete' and native['selected_cases_passed']
        assert native['inputs']['pin'] == PIN and 'crc32' in native['inputs']['modules']
        tree = Path(native['cache']) / 'src'
        library = (tree / 'lib' / ('libswoole.dylib' if sys.platform == 'darwin' else 'libswoole.so')).resolve(strict=True)
        report.update(native_library=str(library),
                      native_original_whole_gate_passed=native['passed'],
                      native_original_unsupported_units=native['excluded_units'])
        address_source = subprocess.check_output(['git', '-C', str(args.source), 'cat-file', 'blob', PIN + ':src/network/address.cc'], timeout=15)
        assert (tree / 'src/network/address.cc').read_bytes() == address_source
        assert (tree / 'src/core/crc32.cc').read_bytes() == (ROOT / 'native/crc32/adapter.cc').read_bytes()
        symbols = run(['nm', '-g', library])
        assert 'swr_v1_crc32' in symbols and 'Address8get_addr' in symbols
        report['commands'][-1]['stdout'] = '\n'.join(line for line in symbols.splitlines() if 'crc32' in line or 'get_addr' in line)
        with tempfile.TemporaryDirectory(prefix='swr-crc-span-', dir='/tmp') as directory:
            scratch = Path(directory)
            oracle = subprocess.check_output(['git', '-C', str(args.source), 'cat-file', 'blob', PIN + ':src/core/crc32.cc'], timeout=15)
            (scratch / 'original.cc').write_bytes(oracle)
            flags = ['-std=c++14', '-O2', '-g', '-UNDEBUG', '-DHAVE_CONFIG_H', '-I'+str(tree), '-I'+str(tree/'include')]
            flags += shlex.split(run(['pkg-config', '--cflags', 'openssl']))
            run(['c++', *flags, '-Dswoole_crc32=original_crc32', '-c', scratch/'original.cc', '-o', scratch/'original.o'])
            links = shlex.split(run(['pkg-config', '--libs', 'openssl', 'libnghttp2']))
            binary = scratch/'probe'
            run(['c++', *flags, Path(__file__).with_suffix('.cc'), scratch/'original.o', '-L'+str(library.parent),
                 '-Wl,-rpath,'+str(library.parent), '-lswoole', *links, '-pthread', '-o', binary])
            report['result'] = json.loads(run([binary, scratch]))
            report['passed'] = report['result']['passed']
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'rows': len(report['result']['rows']), 'fork_copy': report['result']['fork_copy']}))


if __name__ == '__main__':
    main()
