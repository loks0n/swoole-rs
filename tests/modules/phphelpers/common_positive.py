#!/usr/bin/env python3
"""Complete pinned/selected merge/call bodies with positive inert effect recorders.

No historical interruption/destructor/fault matrix, PHP runtime, callback, OOM or
stopped profile executes. Separate Rust-ASan units cover the actual Rust layer.
"""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from gate import ROOT, PIN, stage, body
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error('Use a unique receipt')
    work = output.parent / ('phphelpers-common-positive-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, commands=[], results=[],
                  native_runtime_executed=False, measurement_performed=False, work=str(work))

    def run(command):
        require_build_space(work)
        result = run_isolated(list(map(str, command)), cwd=work, timeout=120)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode or result.stderr:
            raise ValueError('Required positive control failed or warned')
        return result

    try:
        report['sources'] = stage(args.source, work)
        original = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':ext-src/php_swoole_cxx.cc'], text=True)
        selected = (work / 'ext-src/php_swoole_cxx.cc').read_text()
        for engine, common in [('reference', original), ('candidate', selected)]:
            marker = 'static zend_always_inline zval *sw_zend_symtable_str_add('
            begin = common.index(marker if engine == 'reference' else '#ifndef SWOOLE_RS_PHPHELPERS\n' + marker)
            end = common.index('\nnamespace function', begin)
            text = common[begin:end] + '\n' + body(common, 'Callable::Callable(') + '\nnamespace function {\n' + body(common, 'bool call(') + '\n' + body(common, 'Variable call(') + '\n}\n'
            (work / (engine + '-effects.inc')).write_text(text)
        fixture = Path(__file__).with_name('effects.cc').read_text()
        prefix = fixture[:fixture.index('int main() {')]
        (work / 'common-positive-model.inc').write_text(prefix)
        report['additional_compiled_unexecuted_bodies'] = ['Callable::Callable', 'Variable call'];
        archive = work / 'libphphelpers.a'
        run(['rustc', '--edition=2024', '--crate-type=staticlib', '-C', 'opt-level=2', '-D', 'warnings',
             ROOT / 'crates/phphelpers/src/lib.rs', '-o', archive])
        for standard in ['c++14', 'c++17']:
            for sanitize in [False, True]:
                binary = work / (standard + '-' + str(sanitize))
                command = ['c++', '-std=' + standard, '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                           '-DSWOOLE_RS_PHPHELPERS', '-I' + str(work), '-I' + str(ROOT / 'native/phphelpers'),
                           Path(__file__).with_suffix('.cc'), archive, '-lpthread', '-lm', '-o', binary]
                if sys.platform == 'linux':
                    command += ['-ldl']
                if sanitize:
                    command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
                run(command)
                result = json.loads(run([binary]).stdout)
                if result != dict(positive_merges=8, positive_calls=4,
                                  historical_failure_matrix_executed=False, native_runtime_executed=False):
                    raise ValueError('Incomplete positive output')
                report['results'].append(dict(standard=standard, native_cpp_sanitized=sanitize,
                                               rust_instrumented=False, result=result))
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
