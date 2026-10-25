#!/usr/bin/env python3
"""Check actual native sendfile error handling with one explicit EINTR at its syscall boundary."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = (args.source / 'src/network/socket.cc').read_text()
    handle = source[source.index('int Socket::handle_sendfile() {'):source.index('/**\n * send buffer to client')]
    errors = source[source.index('int Socket::catch_error(const int err) {'):source.index('SocketType Socket::convert_to_type')]
    chunk = source[source.index('static size_t get_sendfile_chunk_size'):source.index('int Socket::what_event_want')]
    os_source = (args.source / 'src/os/sendfile.cc').read_text()
    native_os = os_source.replace('#include "swoole_socket.h"', '')
    driver = Path(__file__).with_suffix('.cc').read_text()
    payload = bytes(range(256)) * 32
    report = {'scope': 'Actual extracted handle_sendfile/catch_error/chunk helper and native OS sendfile source, native ASan/UBSan. Explicit minimal Buffer/task/Socket adapter and one injected EINTR, plus a Linux real-signal case; no full object-layout, Rust instruction or whole-reactor claim. Dummy SSL error codes are unexercised; no ABI numeric claim.',
              'source': str(args.source.resolve()), 'results': []}
    with tempfile.TemporaryDirectory(prefix='sendfile-interrupt-') as temp:
        temp = Path(temp)
        (temp / 'payload').write_bytes(payload)
        (temp / 'test.cc').write_text(driver.replace('// ACTUAL_OS_SENDFILE', native_os).replace('// ACTUAL_SOCKET_METHODS', chunk + handle + errors))
        command = ['c++', '-std=c++17', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(temp / 'test.cc'), '-o', str(temp / 'test')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        report['compile'] = {'command': command, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode == 0:
            cases = [('control', ['control']), ('eintr', []), ('eagain', ['eagain']), ('epipe', ['epipe'])]
            if sys.platform.startswith('linux'):
                cases.append(('real-signal-eintr', ['signal']))
            report['real_signal_scope'] = 'Linux only: real SIGALRM without SA_RESTART interrupts native blocking sendfile after filling a real TCP socket; no injected syscall result. Other platforms retain the boundary fault/control only.'
            for name, extra in cases:
                result = subprocess.run([str(temp / 'test'), str(temp / 'payload'), *extra], capture_output=True, text=True, timeout=20)
                report['results'].append({'case': name, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        report['passed'] = report['compile']['exit_code'] == 0 and len(report['results']) == len(cases) and all(r['exit_code'] == 0 for r in report['results'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
