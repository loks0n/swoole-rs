#!/usr/bin/env python3
"""Compare the private Jenkins kernel with the pinned native consumed-width rule.

Large scalar lengths are kernel-only: the public FFI still requires the entire
logical region to be readable. Every actual read here is within a 32-byte array.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated, write_report

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
CPP = r'''
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include "oracle.inc"
int main() {
    static_assert(sizeof(unsigned) == 4 && sizeof(size_t) == 8 && CHAR_BIT == 8);
    for (unsigned high : {0U, 1U, 17U, 0x7fffffffU, 0xffffffffU}) {
        for (unsigned pattern = 0; pattern < 3; ++pattern) {
            char bytes[32];
            for (unsigned i = 0; i < 32; ++i)
                bytes[i] = static_cast<char>(pattern == 0 ? 0 : pattern == 1 ? i + 32 : i * 79 + 128);
            for (unsigned n = 0; n < 32; ++n) {
                size_t length = (static_cast<size_t>(high) << 32) + n;
                assert(static_cast<unsigned>(length) == n);
                std::printf("%llu\n", static_cast<unsigned long long>(swoole_hash_jenkins(bytes, length)));
            }
        }
    }
}
'''
RUST = r'''
fn main() {
    assert_eq!(usize::BITS, 64);
    let signed: bool = std::env::args().nth(1).unwrap() == "signed";
    for high in [0u64, 1, 17, 0x7fffffff, 0xffffffff] {
        for pattern in 0..3 {
            let bytes: [u8; 32] = std::array::from_fn(|i| match pattern {
                0 => 0, 1 => (i + 32) as u8, _ => (i * 79 + 128) as u8,
            });
            for n in 0..32 {
                let length = ((high << 32) + n as u64) as usize;
                assert_eq!(length as u32 as usize, n);
                let expected = hash(&bytes[..n], length, 1, signed);
                // Only these inputs satisfy the frozen full-readable-length FFI contract.
                if high == 0 {
                    assert_eq!(unsafe { swr_v1_utils_hash(bytes.as_ptr(), n, 1, signed as u8) }, expected);
                }
                println!("{expected}");
            }
        }
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--deps', type=Path, required=True, help='Matching private release/deps directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve().parent
    work.mkdir(parents=True, exist_ok=True)
    native = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:src/core/misc.cc'], text=True)
    oracle = native[native.index('#define HASH_JEN_MIX'):native.index('uint64_t swoole_hash_austin')]
    (work / 'oracle.inc').write_text(oracle)
    (work / 'width.cc').write_text('#include <initializer_list>\n' + CPP)
    source = ROOT / 'crates/utilities/src/lib.rs'
    (work / 'width.rs').write_bytes(source.read_bytes() + RUST.encode())
    shutil.copyfile(source.with_name('bytes.rs'), work / 'bytes.rs')
    report = dict(pin=PIN, passed=False, results=[],
                  scope='Private kernel: 480 bounded initialized-prefix cases per char mode, including full-width logical lengths. FFI: only 96 ordinary valid inputs per mode. Native ASan/UBSan; Rust uninstrumented. No large allocation, invalid-memory probe, new FFI precondition or performance claim.')

    def run(command):
        result = run_isolated(command, timeout=60)
        row = dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
        report['results'].append(row)
        write_report(args.output, report)
        if result.returncode:
            raise RuntimeError(json.dumps(row))
        return result.stdout

    deps = args.deps.resolve(strict=True)
    command = ['rustc', '--edition=2024', '-O', str(work / 'width.rs'), '-L', 'dependency=' + str(deps)]
    report['dependencies'] = {}
    for name in ['memchr', 'swoole_rs_locks']:
        paths = list(deps.glob('lib' + name + '-*.rlib'))
        if len(paths) != 1:
            raise ValueError('Ambiguous or missing dependency: ' + str(paths))
        report['dependencies'][name] = str(paths[0])
        command += ['--extern', name + '=' + str(paths[0])]
    rust = work / 'rust-width'
    run(command + ['-o', str(rust)])
    for mode in ['signed', 'unsigned']:
        binary = work / ('native-' + mode)
        run(['c++', '-std=c++17', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
             '-Wno-implicit-fallthrough', '-f' + mode + '-char', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=all', str(work / 'width.cc'), '-o', str(binary)])
        expected = run([str(binary)])
        actual = run([str(rust), mode])
        assert len(expected.splitlines()) == 480 and expected == actual, 'Kernel/native mismatch: ' + mode
        report[mode] = dict(cases=480)
    report['passed'] = True
    write_report(args.output, report)
    print(json.dumps(dict(passed=True, signed=report['signed'], unsigned=report['unsigned'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
