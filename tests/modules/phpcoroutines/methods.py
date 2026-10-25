#!/usr/bin/env python3
"""Exact inert method-table/projector comparison; no Native handlers/Zend/aliases/registration execution."""
import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report
from gate import stage, sha, validate_abi
from method_catalogue_bodies import BRIDGE, declarations, bindings, selected_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true', help='Instrument Native C++ copied-metadata control only; supplied Rust archive is not instrumented')
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcoroutines-methods-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, commands=[], work=str(work),
                  native_handlers_executed=False, zend_registration_executed=False,
                  measurement_performed=False, native_cpp_sanitizers=args.sanitize, rust_archive_instrumented=False,
                  limits=['Copied Native function-address/arginfo tokens with synthetic argument counts; actual SDK compilation is separate.',
                          'No actual method alias, Zend/class/callback/shutdown/GC/lifetime/fault/ZTS/stopped execution.',
                          'Archive ABI/features are observed; producer source attestation remains separate.'])
    def run(command):
        require_build_space(ROOT)
        result = run_isolated(command, timeout=120)
        report['commands'].append(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode: raise ValueError('Method metadata control failed; initial outcome retained')
        return result
    try:
        archive = args.archive.resolve(strict=True)
        report['archive'] = dict(path=str(archive), sha256=sha(archive), source_attested_here=False)
        inputs = [Path(__file__), Path(__file__).with_name('methods.cc'), Path(__file__).with_name('method_catalogue_bodies.py'),
                  ROOT / 'native/phpcoroutines/swoole_rs_phpcoroutines.h'] + list((ROOT / 'crates/phpcoroutines/src').glob('*.rs'))
        report['inputs_sha256'] = {str(path): sha(path) for path in inputs}
        probe = work / 'abi.cc'
        probe.write_text('#include <cstdio>\n#include "swoole_rs.h"\nint main(){std::printf("{\\"abi\\":%u,\\"bits\\":%llu}\\n",swr_v1_abi_version(),static_cast<unsigned long long>(swr_v1_feature_bits()));}\n')
        compiler = os.environ.get('CXX', 'c++')
        abi = work / 'abi'
        run([compiler, '-std=c++14', '-O2', '-I' + str(ROOT / 'native/include'), str(probe), str(archive), '-lpthread', '-ldl', '-lm', '-o', str(abi)])
        observed = json.loads(run([str(abi)]).stdout); validate_abi(observed); report['archive']['observed'] = observed
        tables = []; handlers = set(); infos = set()
        for destination in ('ext-src/swoole_coroutine.cc', 'ext-src/swoole_coroutine_scheduler.cc', 'ext-src/swoole_coroutine_system.cc'):
            original, selected = stage(args.source, work / Path(destination).stem, destination)
            if selected.count(BRIDGE) != 1: raise ValueError('Actual production projector missing/changed')
            for table in declarations(original):
                if selected.count(selected_table(table)) != 1: raise ValueError('Actual production table binding/projection missing')
                tables.append(table)
                for _, value in bindings(table[2]):
                    match = re.search(r'\{(ZEND_(?:MN|FN)\([^)]*\)), (\w+),', value)
                    if not match: raise ValueError('Unknown Native binding format')
                    handlers.add(match[1]); infos.add(match[2])
        definitions = 'volatile uint32_t model_handler_observation = 0;\n'
        for ordinal, handler in enumerate(sorted(handlers), 1):
            definitions += f'void {handler}() {{ model_handler_observation = {ordinal}; }}\n'
        for i, name in enumerate(sorted(infos)):
            definitions += f'extern const zend_internal_arg_info {name}[{1 + i % 6}] = {{}};\n'
        for table in tables:
            definitions += table[0].replace(table[1], 'expected_' + table[1], 1) + '\n'
        definitions += BRIDGE
        for table in tables: definitions += selected_table(table) + '\n'
        fixture = Path(__file__).with_name('methods.cc').read_text().replace('// EXACT_TABLES_AND_PROJECTOR', definitions)
        source = work / 'methods.cc'; source.write_text(fixture)
        report['profiles'] = []
        for enabled in (False, True):
            binary = work / ('time-' + str(int(enabled)))
            flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
            command = [compiler, '-std=c++14', '-O2', '-Wall', '-Wextra', '-Werror', *flags, '-DSWOOLE_RS_PHPCOROUTINES=1',
                       '-I' + str(ROOT / 'native/phpcoroutines'), *(['-DSW_CORO_TIME=1'] if enabled else []),
                       str(source), str(archive), '-lpthread', '-ldl', '-lm', '-o', str(binary)]
            run(command); result = json.loads(run([str(binary)]).stdout)
            if result != dict(rows=57 if enabled else 56, tables=4, matched=True): raise ValueError('Unexpected method control output')
            report['profiles'].append(dict(SW_CORO_TIME=enabled, result=result))
        if sha(archive) != report['archive']['sha256'] or any(sha(path) != digest for path, digest in report['inputs_sha256'].items()):
            raise ValueError('Inputs changed during method controls')
        report['passed'] = True
    except Exception as error: report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
