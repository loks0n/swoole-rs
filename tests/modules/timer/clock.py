#!/usr/bin/env python3
"""Actual complete original/selected OS timer TU: scalar/errno/syscall argument parity."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import run_isolated, write_report


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--control-source', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    source = Path(manifest['extension']).parents[1]
    prefix = source.parent / 'rust-prefix'
    archive = prefix / 'lib/libswoole_rs_ffi.a'
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Actual complete OS timer TUs with intercepted setitimer execution boundary; native errno/arguments/order, realtime_add including negative additions, actual clock acquisition. No actual kernel signal or performance claim; separate original timer.sys exercises kernel.',
              'native_sanitized': args.sanitize, 'rust_instrumented': False, 'engines': []}
    try:
        assert sha(Path(manifest['extension'])) == manifest['extension_sha256']
        assert sha(archive) == manifest['inputs']['rust_archive_sha256']
        outputs = []
        with tempfile.TemporaryDirectory(prefix='timer-clock-') as tmp:
            for name, tree in [('control', args.control_source.resolve()), ('rust', source)]:
                os_source = tree / 'src/os/timer.cc'
                binary = Path(tmp) / name
                command = shlex.split(os.environ.get('CXX', 'c++')) + ['-std=c++17', '-O1', '-g', '-ffunction-sections', '-fdata-sections', '-DHAVE_CONFIG_H',
                           '-I' + str(tree), '-I' + str(tree / 'include'), '-DSWR_TIMER_OS_SOURCE="' + str(os_source) + '"',
                           str(Path(__file__).with_suffix('.cc')), '-o', str(binary)]
                if name == 'rust':
                    command += ['-DSWOOLE_RS_TIMER=1', '-I' + str(prefix / 'include'), str(archive)]
                if sys.platform == 'darwin':
                    command += ['-Wl,-dead_strip']
                    for option in manifest['configure']:
                        if option.startswith('--with-openssl-dir='):
                            command += ['-I' + option.split('=', 1)[1] + '/include']
                else:
                    command += ['-Wl,--gc-sections', '-ldl', '-lpthread', '-lrt', '-lutil', '-lm']
                if args.sanitize:
                    command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
                compiled = run_isolated(command, timeout=90)
                row = {'engine': name, 'compile': command,
                       'compile_returncode': compiled.returncode, 'compile_stdout': compiled.stdout, 'compile_stderr': compiled.stderr}
                report['engines'].append(row)
                if compiled.returncode:
                    raise RuntimeError(name + ' compile failed')
                result = run_isolated([str(binary)], timeout=10)
                row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                if result.returncode:
                    raise RuntimeError(name + ' execution failed')
                outputs.append(result.stdout)
        report['rows'] = len(outputs[0].splitlines())
        report['passed'] = outputs[0] == outputs[1] and report['rows'] == 734
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'rows': report.get('rows'), 'error': report.get('error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
