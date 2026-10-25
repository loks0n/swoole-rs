#!/usr/bin/env python3
"""Compare complete original and patched base.cc through actual native callers."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import tempfile
from patching import apply_corebase, check_git_environment, prove_calls
from cases import generate

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Configured pinned upstream checkout (read-only)')
    parser.add_argument('--include', type=Path, action='append', default=[], help='Additional dependency include directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='Exact published Rust static archive; otherwise compile owned source privately')
    char_mode = parser.add_mutually_exclusive_group()
    char_mode.add_argument('--signed-char', action='store_true', help='Validate native -fsigned-char mode')
    char_mode.add_argument('--unsigned-char', action='store_true', help='Validate native -funsigned-char mode including all byte ctype inputs')
    parser.add_argument('--sanitize', action='store_true', help='Native ASan/UBSan only; Rust instrumentation is separate')
    args = parser.parse_args()
    report = {'passed': False, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'upstream_commit': PIN, 'commands': [],
              'scope': 'Eight helpers via complete original/patched native TU, configured native strndup allocation; no PHP, full base lifecycle or performance claim.',
              'native_sanitizers': args.sanitize, 'rust_sanitizers': 'external archive: inspect its provenance' if args.archive else False, 'native_long_bits': __import__('ctypes').sizeof(__import__('ctypes').c_long) * 8,
              'exclusions': ['decimal LONG_MIN: original signed overflow', 'high-bit hex ctype inputs',
                             'zero gcd/lcm and invalid radix native assertion domains',
                             'lcm intermediate remainder above INT_MAX: native implementation-defined conversion',
                             'unavailable host locales explicitly counted, never passes']}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def run(argv, cwd=None, data=None):
        env = os.environ.copy()
        if args.sanitize:
            env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
            env['ASAN_OPTIONS'] = 'abort_on_error=1:detect_leaks=' + ('0' if platform.system() == 'Darwin' else '1')
        process = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = process.communicate(data, timeout=60)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report['commands'].append({'argv': list(map(str, argv)), 'interrupted': True,
                                       'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace')})
            raise
        report['commands'].append({'argv': list(map(str, argv)), 'returncode': process.returncode,
                                   'stderr': stderr.decode(errors='replace')})
        if process.returncode:
            raise RuntimeError('Command failed; original diagnostics retained in report')
        return stdout

    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    try:
        check_git_environment()
        source = args.source.resolve()
        original = run(['git', '-C', source, 'show', PIN + ':src/core/base.cc'])
        manifest = json.loads((ROOT / 'migration/patches/corebase/manifest.json').read_text())
        assert manifest['upstream_commit'] == PIN and len(manifest['patches']) == 1
        entry = manifest['patches'][0]
        assert entry['upstream_paths'] == ['src/core/base.cc']
        patch = ROOT / 'migration/patches/corebase' / entry['path']
        assert digest(patch) == entry['sha256']
        cases = generate(args.unsigned_char)
        inputs = ''.join(f"{c['id']} {c['operation']} {c['locale']} {c['initial_errno']} {c['a'] or '-'} {c['b'] or '-'}\n" for c in cases).encode()
        args.output.with_suffix('.inputs').write_bytes(inputs)
        with tempfile.TemporaryDirectory(prefix='swoole-corebase-') as temporary:
            work = Path(temporary)
            (work / 'src/core').mkdir(parents=True)
            target = work / 'src/core/base.cc'
            target.write_bytes(original)
            report['patch_application'] = apply_corebase(work, patch, run, entry['sha256'])
            patched = target.read_bytes()
            original_tests = run(['git', '-C', source, 'show', PIN + ':core-tests/src/core/base.cpp']).decode()
            selected = ['dec2hex', 'hex2dec', 'version_compare', 'common_divisor', 'common_multiple', 'dirname', 'itoa', 'type_size']
            bodies = []
            for name in selected:
                start = original_tests.index('TEST(base, ' + name + ')')
                opening = original_tests.index('{', start)
                depth = 1;end = opening + 1
                while depth:
                    depth += (original_tests[end] == '{') - (original_tests[end] == '}')
                    end += 1
                bodies.append(original_tests[start:end])
            original_driver = work / 'original-tests.cc'
            original_driver.write_text('#include "swoole.h"\n#include "swoole_protocol.h"\n#include <cstdlib>\n#include <cstring>\nusing namespace swoole;\n#define TEST(group,name) void test_##name()\n#define ASSERT_EQ(a,b) do { if (!((a)==(b))) std::abort(); } while(0)\n#define ASSERT_STREQ(a,b) do { if (std::strcmp((a),(b)) != 0) std::abort(); } while(0)\n' + '\n'.join(bodies) + '\nint main(){SwooleG.std_allocator={malloc,calloc,realloc,free};' + ''.join('test_' + n + '();' for n in selected) + '}\n')
            report['original_test_cases'] = selected
            report['allocation_gate'] = 'Standard strndup interposition: one allocation, exact length/NUL, reentrant helper call, ENOMEM/null, retry; both engines'
            if args.archive:
                archive = args.archive.resolve()
            else:
                (work / 'Cargo.toml').write_text('[workspace]\n[package]\nname="corebase-gate"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nitoa="=1.0.18"\n[lib]\nname="swoole_rs_corebase"\ncrate-type=["staticlib"]\npath=' + json.dumps(str(ROOT / 'crates/corebase/src/lib.rs')) + '\n')
                run(['cargo', 'build', '--offline', '--release', '--manifest-path', work / 'Cargo.toml'])
                archive = work / 'target/release/libswoole_rs_corebase.a'
            flags = ['-std=c++17', '-O2', '-ffunction-sections', '-fdata-sections', '-DHAVE_CONFIG_H', '-I' + str(source), '-I' + str(source / 'include')]
            flags += ['-I' + str(i.resolve()) for i in args.include]
            if args.unsigned_char:
                flags += ['-funsigned-char']
            elif args.signed_char:
                flags += ['-fsigned-char']
            report['native_char_mode'] = 'unsigned' if args.unsigned_char else ('signed' if args.signed_char else 'compiler default')
            if args.sanitize:
                flags += ['-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            link = ['-Wl,-dead_strip'] if platform.system() == 'Darwin' else ['-Wl,--gc-sections', '-ldl', '-lpthread', '-lm']
            outputs = {}
            for engine, body in [('original', original), ('rust', patched)]:
                src = work / (engine + '.cc');src.write_bytes(body)
                obj = work / (engine + '.o');binary = work / engine
                extra = ['-DSWOOLE_RS_COREBASE', '-I' + str(ROOT / 'native/corebase')] if engine == 'rust' else []
                run(['c++', *flags, *extra, '-c', src, '-o', obj])
                run(['c++', *flags, ROOT / 'tests/modules/corebase/driver.cc', obj, *([archive] if engine == 'rust' else []), *link, '-o', binary])
                report.setdefault('actual_calls', {})[engine] = prove_calls(binary,
                    ['type_size', 'gcd', 'lcm', 'parse_stoi', 'itoa', 'radix', 'hex_mode', 'version', 'dirname'],
                    engine == 'rust', run, args.output.with_suffix('.' + engine))
                test_binary = work / (engine + '-original-tests')
                run(['c++', *flags, original_driver, obj, *([archive] if engine == 'rust' else []), *link, '-o', test_binary])
                run([test_binary])
                allocator_binary = work / (engine + '-allocator')
                run(['c++', *flags, ROOT / 'tests/modules/corebase/allocator.cc', obj, *([archive] if engine == 'rust' else []), *link, '-o', allocator_binary])
                run([allocator_binary])
                outputs[engine] = run([binary], data=inputs)
                args.output.with_suffix('.' + engine + '.tsv').write_bytes(outputs[engine])
            assert outputs['original'] == outputs['rust'], 'Native/Rust output or errno mismatch'
            rows = outputs['original'].decode().splitlines()
            assert len(rows) == len(cases)
            available = expected = unavailable = 0
            for case, row in zip(cases, rows):
                fields = row.split('\t');assert fields[0] == case['id']
                if fields[1] == 'UNAVAILABLE':
                    unavailable += 1
                    continue
                available += 1
                if case['expected_value'] is not None:
                    assert fields[1] == case['expected_value'], (case, row)
                    expected += 1
            report.update(passed=True, cases=len(cases), matched=available, unavailable=unavailable,
                          independent_expected_checks=expected)
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['passed', 'cases', 'matched', 'unavailable', 'independent_expected_checks']}))


if __name__ == '__main__':
    main()
