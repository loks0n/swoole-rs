#!/usr/bin/env python3
"""Ordinary C11/C++14 ABI consumers of a private M29-only or supplied selected archive; no PHP or measurement."""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from gate import sha, validate_abi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Consume an immutable production archive, validating genuine ABI1/M29 bit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcoroutines-ffi-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, commands=[], work=str(work), measurement_performed=False,
                  php_executed=False, limits=['Pure ABI/metadata consumers, not Zend/coroutine/native lifecycle or original proof.',
                                             'Optimized compilation is not a performance measurement.'])
    def run(command, env=None):
        require_build_space(ROOT)
        result = run_isolated(command, timeout=120, env=env)
        report['commands'].append(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode:
            raise ValueError('FFI preparation/consumer failed; initial outcome retained')
        return result
    try:
        inputs = [ROOT / name for name in ('Cargo.toml', 'Cargo.lock', 'crates/ffi/Cargo.toml', 'crates/ffi/src/lib.rs',
                                           'crates/phpcoroutines/Cargo.toml', 'native/include/swoole_rs.h',
                                           'native/phpcoroutines/swoole_rs_phpcoroutines.h', 'tests/modules/phpcoroutines/ffi.c')]
        inputs += list((ROOT / 'crates/phpcoroutines/src').glob('*.rs'))
        report['inputs_sha256'] = {str(path): sha(path) for path in inputs}
        if args.archive:
            archive = args.archive.resolve(strict=True)
            report['archive_identity'] = dict(mode='supplied selected archive', path=str(archive), sha256=sha(archive),
                source_attestation='ABI/feature and symbol consumers only; producer manifest must bind the supplied archive to production source.')
        else:
            env = os.environ.copy()
            env['CARGO_TARGET_DIR'] = str(work / 'cargo')
            result = run(['cargo', 'build', '--offline', '--locked', '-p', 'swoole-rs-ffi', '--release',
                          '--no-default-features', '--features', 'phpcoroutines', '--message-format=json-render-diagnostics'], env)
            messages = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            artifacts = [row for row in messages if row.get('reason') == 'compiler-artifact'
                         and row['target']['name'] == 'swoole_rs_ffi']
            archives = [(row, path) for row in artifacts for path in row['filenames'] if path.endswith('.a')]
            if len(archives) != 1:
                raise ValueError('Ambiguous Cargo static archive')
            row, path = archives[0]
            archive = Path(path)
            report['cargo_artifact'] = dict(path=path, features=row['features'], profile=row['profile'])
            report['archive_identity'] = dict(mode='fresh M29-only Cargo archive', path=str(archive), sha256=sha(archive))
        for standard, compiler in [('c11', os.environ.get('CC', 'cc')), ('c++14', os.environ.get('CXX', 'c++'))]:
            binary = work / standard
            command = [compiler, '-x', 'c' if standard == 'c11' else 'c++', '-std=' + standard, '-O2', '-Wall', '-Wextra', '-Werror',
                       '-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/phpcoroutines'),
                       *(['-DSWR_M29_SUPPLIED_ARCHIVE'] if args.archive else []),
                       str(ROOT / 'tests/modules/phpcoroutines/ffi.c'), '-x', 'none', str(archive), '-lpthread', '-ldl', '-lm', '-o', str(binary)]
            run(command)
            result = run([str(binary)])
            if args.archive:
                identity = json.loads(result.stdout)
                validate_abi(identity)
                if identity.get('passed') is not True or set(identity) != {'abi', 'bits', 'passed'}:
                    raise ValueError('Unexpected supplied-archive consumer output')
                report['archive_identity'][standard] = identity
            elif result.stdout != 'M29_ONLY_FFI_OK\n':
                raise ValueError('Unexpected ABI consumer output')
            report[standard] = dict(output=result.stdout)
        if sha(archive) != report['archive_identity']['sha256']:
            raise ValueError('Archive changed during ABI consumption')
        if any(sha(path) != digest for path, digest in report['inputs_sha256'].items()):
            raise ValueError('Inputs changed during preparation')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
