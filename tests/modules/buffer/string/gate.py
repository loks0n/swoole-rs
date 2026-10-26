#!/usr/bin/env python3
"""Run unchanged upstream String assertions plus owned-storage behavior checks."""
import argparse
import hashlib
import io
import json
import re
import shlex
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tools.harness import ROOT, run_isolated, write_report
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from staging import apply_module_patch
from tools.build_upstream import COMMIT as PIN
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def ownership_inventory(outcome, selected):
    return outcome == {'checks': 13, 'selected_origin_checks': 3 if selected else 0}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--patch', type=Path, default=ROOT / 'migration/patches/buffer/0003-string-storage.patch')
    parser.add_argument('--rust-source', type=Path, default=ROOT / 'crates/buffer/src/string.rs', help='Rust String source whose declared submodules must exist')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--random-only', action='store_true', help='Only ordinary positive1..1024 entropy/codec consumers; no zero or injected failures')
    parser.add_argument('--format-only', action='store_true', help='Only whole positive variadic format/append workflows; native effects remain outside Rust')
    parser.add_argument('--allocation-only', action='store_true', help='Only positive initialized allocation metadata/native offset effects and caught reserve OOM')
    parser.add_argument('--ownership-only', action='store_true', help='Only positive assignment/destructor custody and live pre-free metadata')
    parser.add_argument('--transition-only', action='store_true', help='Only defined positive ownership/capacity transitions; no original unsafe-edge probes')
    parser.add_argument('--copy-only', action='store_true', help='Only positive copy/provenance and caught constructor OOM; no original unsafe-edge probes')
    parser.add_argument('--split-only', action='store_true', help='Only positive callback continuations; no original unsafe-edge probes')
    parser.add_argument('--integer-only', action='store_true', help='Only defined integer append/storage and caught realloc OOM')
    parser.add_argument('--original-only', action='store_true', help='All23 unchanged pinned original String tests, no added edge groups')
    parser.add_argument('--rust-asan', action='store_true', help='Supplied archive was separately compiled with Rust address sanitizer')
    parser.add_argument('--prepare-benchmark', type=Path, help='Compile optimized consumers and check their workloads without timing')
    parser.add_argument('--output', default='target/reports/string-gate.json')
    args = parser.parse_args()
    if sum([args.random_only, args.format_only, args.allocation_only, args.ownership_only, args.transition_only, args.copy_only, args.split_only, args.integer_only, args.original_only, bool(args.prepare_benchmark)]) > 1: parser.error('Choose one qualification/preparation profile')
    if not any([args.random_only, args.format_only, args.allocation_only, args.ownership_only, args.transition_only, args.copy_only, args.split_only, args.integer_only, args.original_only, args.prepare_benchmark]):
        parser.error('Choose a qualification/preparation profile')
    for module in re.findall(r'^mod (\w+);$', args.rust_source.read_text(), re.MULTILINE):
        path = args.rust_source.with_suffix('') / (module + '.rs')
        if not path.is_file(): parser.error('Missing selected Rust source module: ' + str(path))
    if args.rust_asan:
        if not args.sanitize: parser.error('Rust ASan archive requires the native sanitizer runtime')
        symbols = subprocess.run(['nm', '-u', str(args.archive)], capture_output=True, text=True)
        if '__asan_report_' not in symbols.stdout: parser.error('Selected archive lacks Rust ASan report imports')
    if args.prepare_benchmark and args.sanitize: parser.error('Benchmark preparation cannot use sanitizers')
    if args.prepare_benchmark: args.prepare_benchmark = args.prepare_benchmark.resolve(); args.prepare_benchmark.mkdir(parents=True, exist_ok=True)
    local = Path(__file__).resolve().parent
    report = {'passed': False, 'pin': PIN, 'sanitize_cpp_only': args.sanitize and not args.rust_asan,
              'rust_asan_declared': args.rust_asan, 'positive_random_only': args.random_only, 'positive_format_only': args.format_only, 'positive_allocation_only': args.allocation_only, 'positive_ownership_only': args.ownership_only, 'positive_transition_only': args.transition_only, 'positive_copy_only': args.copy_only, 'positive_split_only': args.split_only, 'positive_integer_only': args.integer_only, 'original_only': args.original_only,
              # string/benchmark.py refuses to compare prepared reports built from different benchmark.cc.
              'adapter_sha256': {'benchmark.cc': sha(local / 'benchmark.cc')}, 'engines': {}}
    with tempfile.TemporaryDirectory(prefix='swr-string-') as temp:
        tree = Path(temp)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree / member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        tests = tree / 'string.cpp'
        tests.write_bytes(subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':core-tests/src/core/string.cpp']))
        original_ids = ['.'.join(match) for match in re.findall(r'^TEST\(\s*(\w+)\s*,\s*(\w+)\s*\)', tests.read_text(), re.MULTILINE)]
        report['original_inventory'] = original_ids
        if args.original_only and len(original_ids) != 23:
            raise ValueError('Pinned original String inventory differs from23')
        for engine in ['upstream', 'rust']:
            if engine == 'rust':
                patch = args.patch.resolve()
                report['patch_application'] = [apply_module_patch(tree, patch, allow_override=True)]
            binary = (args.prepare_benchmark or tree) / engine
            command = ['c++', '-std=c++17', '-O3' if args.prepare_benchmark else '-O1', '-g', '-ffunction-sections', '-fdata-sections',
                       '-I' + str(local), '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/buffer'),
                       *[str(tree / name) for name in ['src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc']],
                       *([str(tests)] if args.original_only else []), str(local / ('benchmark.cc' if args.prepare_benchmark else 'random.cc' if args.random_only else 'formatting.cc' if args.format_only else 'allocation.cc' if args.allocation_only else 'ownership.cc' if args.ownership_only else 'transitions.cc' if args.transition_only else 'copy.cc' if args.copy_only else 'split-continuation.cc' if args.split_only else 'integers.cc' if args.integer_only else 'originals.cc'))]
            command += shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'openssl'], text=True))
            if engine == 'rust': command += ['-DSWR_STRING_RUST_GATE', str(args.archive.resolve())]
            command += ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm']
            if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            if args.sanitize: command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
            command += ['-o', str(binary)]
            row = report['engines'][engine] = {'compile_command': command}
            compiled = run_isolated(command, timeout=60)
            row['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
            if compiled.returncode:
                write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
            row['binary_sha256'] = sha(binary)
            row['binary'] = str(binary)
            if engine == 'rust':
                symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
                # Exports the profile's native callers reach; Rust-only callees may be inlined or stripped.
                required = ['swr_v1_string_edit_in_place', 'swr_v1_string_append_in_place'] if args.original_only else ['swr_v1_string_transition']
                if args.random_only: required.append('swr_v1_string_random_step')
                if args.format_only: required.append('swr_v1_string_format_step')
                if args.allocation_only: required.append('swr_v1_string_allocation_plan')
                if args.ownership_only: required.append('swr_v1_string_ownership_plan')
                if args.split_only: required.append('swr_v1_string_split_plan')
                assert all(name in symbols for name in required)
            if args.prepare_benchmark:
                row['untimed_checks'] = {}
                for workload in ['append-4k', 'append-cold', 'repeat-4k', 'write-reduce', 'query-4k', 'split-4k', 'split-missing', 'query-dense', 'query-dense-long', 'append-integer', 'append-integer-cold']:
                    checked = run_isolated([str(binary), workload, 'check'], timeout=30)
                    row['untimed_checks'][workload] = {'returncode': checked.returncode, 'stdout': checked.stdout, 'stderr': checked.stderr}
                    if checked.returncode:
                        write_report(args.output, report); print(checked.stderr, file=sys.stderr); return 1
                continue
            result = run_isolated([str(binary)], timeout=30)
            row['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
            if result.returncode:
                write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
            row['outcome'] = json.loads(result.stdout.splitlines()[-1])
            if args.random_only and row['outcome'] != {'checks': 673}:
                report['error'] = 'Positive entropy assertion inventory differs'
                write_report(args.output, report); return 1
            if args.format_only and row['outcome'] != {'checks': 604}:
                report['error'] = 'Formatting assertion inventory differs'
                write_report(args.output, report); return 1
            if args.allocation_only and row['outcome'] != {'checks': 12}:
                report['error'] = 'Allocation assertion inventory differs'
                write_report(args.output, report); return 1
            if args.ownership_only and not ownership_inventory(row['outcome'], engine == 'rust'):
                report['error'] = 'Ownership assertion inventory differs'
                write_report(args.output, report); return 1
            if args.original_only and (row['outcome'].get('original_ids') != original_ids or row['outcome'].get('failed') != 0):
                report['error'] = 'Original named inventory/outcomes differ'
                write_report(args.output, report); return 1
        if args.prepare_benchmark:
            report['prepared'] = True
            assert len({row['binary_sha256'] for row in report['engines'].values()}) == 2
            write_report(args.output, report); print('Prepared ' + args.output); return 0
        report['passed'] = True
        write_report(args.output, report)
        print(json.dumps({name: row['outcome'] for name, row in report['engines'].items()}))
    return 0
if __name__ == '__main__': sys.exit(main())
