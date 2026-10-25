#!/usr/bin/env python3
"""Compare the Rust codec with unchanged pinned C++ codec function bodies."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.harness import run_compiler

from tools.build_upstream import COMMIT as PIN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--archive', type=Path, default=ROOT / 'target/release/libswoole_rs_ffi.a')
    parser.add_argument('--output', default=str(ROOT / 'target/reports/websocket-codec.json'))
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-asan', action='store_true', help='declare externally instrumented Rust archive; requires ASan imports')
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    if args.rust_asan:
        if not args.sanitize:
            parser.error('--rust-asan requires --sanitize')
        symbols = subprocess.run(['nm', '-u', str(archive)], capture_output=True, text=True)
        if '__asan_report_' not in symbols.stdout:
            parser.error('Selected archive lacks Rust ASan report imports')
    local = Path(__file__).resolve().parent
    source = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:src/protocol/websocket.cc'], text=True)
    php_source = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:ext-src/swoole_websocket_server.cc'], text=True)
    core_header = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:include/swoole.h'], text=True)
    bit_macros = '\n'.join(line for line in core_header.splitlines() if line.startswith(('#define sw_unset_bit(', '#define sw_set_bit(')))
    if len(bit_macros.splitlines()) != 2:
        raise ValueError('Pinned bit macros differ; review exact macro definitions')
    header = subprocess.check_output(['git', '-C', str(args.source), 'show', f'{PIN}:include/swoole_websocket.h'], text=True)
    # Keep the actual codec bodies unchanged. Only its storage/logging dependencies
    # are adapted: no sockets/PHP/allocator policy belong to this differential.
    functions = source[source.index('static ssize_t get_package_length_impl'):source.index('void print_frame(')]
    types = header[header.index('enum Flag {'):header.index('#define WEBSOCKET_VERSION')]
    opcodes = header[header.index('enum Opcode {'):header.index('enum CloseReason {')]
    constants = '\n'.join(line for line in header.splitlines() if line.startswith('#define SW_WEBSOCKET_'))
    adapter = r'''
#include <arpa/inet.h>
#include <cinttypes>
#include <cstdint>
#include <cstring>
#include <vector>
#define swoole_trace_log(...) ((void)0)
#define swoole_error_log(...) ((void)0)
#define swoole_warning(...) ((void)0)
#define sw_unlikely(value) (value)
namespace reference {
using uchar = unsigned char;
struct Protocol {};
struct Socket {};
struct PacketLength { const char *buf; uint32_t buf_size; uint32_t header_len; };
struct String {
    std::vector<char> bytes;
    char *str = nullptr;
    size_t length = 0;
    void append(const char *data, size_t size) {
        if (!size) return;
        bytes.insert(bytes.end(), data, data + size);
        str = bytes.data(); length = bytes.size();
    }
};
static uint64_t swoole_ntoh64(uint64_t value) {
    unsigned char bytes[8]; std::memcpy(bytes, &value, 8);
    uint64_t result = 0;
    for (auto byte : bytes) result = (result << 8) | byte;
    return result;
}
static uint64_t swoole_hton64(uint64_t value) { return swoole_ntoh64(value); }
'''
    # Compile the actual pinned PHP-facing policy snippets, without maintaining
    # a second C++ translation of their branches. Zend/zlib/socket execution is
    # deliberately excluded; the extension/network gates cover those callers.
    pack = php_source[php_source.index('    bool need_compress ='):php_source.index('    if (need_compress)')]
    begin = php_source.index('    if ((opcode == WebSocket::OPCODE_CLOSE')
    end = php_source.index(' {', begin)
    visibility = php_source[begin + len('    if ('):end - 1]
    policy = r'''
namespace WebSocket = reference;
''' + bit_macros + r'''
uint16_t pack_policy(uint8_t opcode, uint8_t flags, size_t len) {
''' + pack + r'''
    return uint16_t(flags) | (uint16_t(need_compress) << 8);
}
uint8_t message_policy(uint8_t opcode, uint8_t settings) {
    struct Settings { bool open_close_frame, open_ping_frame, open_pong_frame; };
    struct Port { Settings websocket_settings; } value{{bool(settings & 1), bool(settings & 2), bool(settings & 4)}};
    auto *port = &value;
    const bool drop = ''' + visibility + r''';
    return drop ? (opcode == OPCODE_PING ? 2 : 1) : 0;
}
'''
    oracle = adapter + constants + '\n' + types + opcodes + functions + policy + '\n}\n'
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': PIN,
              'archive': str(archive),
              'rust_asan_declared': args.rust_asan,
              'sanitizer_scope': ('C++ caller ASan/UBSan excluding upstream unaligned integer loads; ' +
                                  ('WebSocket Rust instructions ASan, prebuilt Rust stdlib not instrumented' if args.rust_asan else
                                   'Rust not instrumented')) if args.sanitize else 'none',
              'scope': 'Unchanged pinned encode/decode/close bodies with vector String/log adapters and exact PHP pack/message policy snippets; explicit dispatch cases are not a differential of socket dispatch'}
    with tempfile.TemporaryDirectory(prefix='swr-websocket-codec-') as directory:
        tree = Path(directory)
        (tree / 'oracle.inc').write_text(oracle)
        binary = tree / 'codec'
        command = shlex.split(os.environ.get('CXX', 'c++')) + [
            '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
            '-I' + str(tree), '-I' + str(ROOT / 'native/websocket'),
            str(local / 'codec.cc'), str(archive), '-lc', '-lm']
        if sys.platform.startswith('linux'):
            command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize=alignment', '-fno-sanitize-recover=all']
        report['compile'] = run_compiler(command + ['-o', str(binary)])
        if report['compile']['returncode']:
            write_report(args.output, report)
            print(report['compile']['stderr'], file=sys.stderr)
            return 1
        result = run_isolated([str(binary)], timeout=60)
        report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        report['passed'] = result.returncode == 0
        if not result.returncode:
            report['outcome'] = json.loads(result.stdout)
        write_report(args.output, report)
        print(result.stdout if not result.returncode else result.stderr, end='')
        return int(result.returncode != 0)


if __name__ == '__main__':
    sys.exit(main())
