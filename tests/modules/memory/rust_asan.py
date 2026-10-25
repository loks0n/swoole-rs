#!/usr/bin/env python3
"""Run the real memory Rust unit tests with installed-compiler ASan instrumentation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    paths = sorted((ROOT / 'crates/memory/src').glob('*.rs'))
    paths += sorted((ROOT / 'tests/modules/memory').glob('*.rs'))
    return {str(path.relative_to(ROOT)): sha(path) for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rustc', default='rustc')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix=output.stem + '-', dir=output.parent))
    before = sources()
    report = {'passed': False, 'platform': platform.platform(),
              'artifacts': str(artifacts), 'scope': 'Actual Rust memory unit instructions with AddressSanitizer. Precompiled standard library, native facades, PHP, process-shared/fork behavior and performance are not covered.'}
    environment = dict(os.environ, RUSTC_BOOTSTRAP='1',
                       ASAN_OPTIONS='detect_leaks=' + ('1' if platform.system() == 'Linux' else '0'))
    report['environment'] = {key: environment[key] for key in ['RUSTC_BOOTSTRAP', 'ASAN_OPTIONS']}

    def run(name, command):
        process = subprocess.Popen(command, cwd=ROOT, env=environment, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        timed_out = False
        try:
            text, _ = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            text, _ = process.communicate()
        log = artifacts / (name + '.log')
        log.write_text(text)
        report[name] = {'command': command, 'exit_code': process.returncode,
                        'timed_out': timed_out, 'log': str(log)}
        if timed_out or process.returncode:
            raise ValueError(f'{name} failed: see {log}')
        return text

    try:
        if platform.system() not in ['Darwin', 'Linux']:
            raise ValueError('Only installed macOS/Linux sanitizer runtimes are supported')
        run('compiler', [args.rustc, '-vV'])
        binary = artifacts / 'memory-tests'
        run('build', [args.rustc, '--edition=2024', '-Zsanitizer=address', '-C', 'opt-level=1',
                      '-C', 'debuginfo=1', '--test', '--emit=llvm-ir,link',
                      'crates/memory/src/lib.rs', '-o', str(binary)])
        ir = binary.with_suffix('.ll')
        instructions = ir.read_text()
        if 'sanitize_address' not in instructions or not re.search(r'call void @__asan_report_', instructions):
            raise ValueError('Compiler output lacks actual address-sanitized instructions')
        listed = run('inventory', [str(binary), '--list'])
        expected = len(re.findall(r'^.+: test$', listed, re.M))
        if not expected:
            raise ValueError('No real unit tests inventoried')
        tests = run('tests', [str(binary)])
        summary = re.search(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', tests)
        if not summary or tuple(map(int, summary.groups())) != (expected, 0, 0, 0, 0):
            raise ValueError('Tests did not all pass without omissions')
        if before != sources():
            raise ValueError('Sources changed during sanitizer validation')
        report['tests_passed'] = expected
        report['passed'] = True
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        report['error'] = f'{type(error).__name__}: {error}'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'tests_passed': report.get('tests_passed'),
                      'report': str(output), 'error': report.get('error')}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
