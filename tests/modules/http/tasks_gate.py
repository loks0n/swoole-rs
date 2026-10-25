#!/usr/bin/env python3
"""Actual sole-Rust V2 range/task owner and copied Native send snapshot, normal controls only."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_static_header, prepare_workload, add_archive_arguments, prepare_archive, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--prepare', type=Path, help='New immutable optimized task artifact; untimed verification only')
    parser.add_argument('--output', default='target/reports/http-tasks.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    if args.prepare and args.rust_sanitize: parser.error('--prepare requires an optimized uninstrumented archive')
    if args.prepare and args.prepare.exists(): parser.error('--prepare destination must not already exist')
    patch = ROOT/'migration/patches/http/0002-static-ranges.patch'
    report = {'pin': PIN, 'scope': 'Actual original range/content bodies versus real V2 task owner/copy/content callers and Rust storage; Native MIME/boundary/date facades and transient IO snapshot, not full filesystem/PHP/IO/lifetime parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False, 'full_gate_passed': False, 'unrun_profiles': ['allocation/errors/partial/fault profiles', 'reentry/response/process lifetimes', 'full filesystem/PHP/original/runtime', 'performance']}

    with tempfile.TemporaryDirectory(prefix='swr-http-tasks-') as temp:
        tree = Path(temp)
        if not prepare_archive(args, tree, report):
            write_report(args.output, report)
            return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/server/static_handler.cc'; original = source.read_text()
        apply_http_patch(tree, patch, report)
        apply_static_header(tree, report)
        flags = ['-std=c++17', '-DSWOOLE_RS_HTTP', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-I'+str(tree), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        header = (ROOT/'native/http/swoole_rs_http_static_v2.h').read_text()
        typed = body(header, 'class StaticHandlerV2')
        (tree/'tasks_candidate.h').write_text('#pragma once\nnamespace candidate_tasks {\n'+typed+';\n}\n')
        selected = source.read_text()
        signatures = ['StaticHandlerV2::StaticHandlerV2(', 'StaticHandlerV2::~StaticHandlerV2(', 'static size_t prepare_range_task(', 'void StaticHandlerV2::parse_range(', 'std::vector<swr_v2_http_static_task> StaticHandlerV2::copy_tasks(', 'const std::string &StaticHandlerV2::get_content_type(']
        selected_bodies = typed + '\n'.join(body(selected, signature) for signature in signatures)
        report['native_authoritative_task_mirror_absent'] = 'core_.tasks' not in selected_bodies and 'core_.get_tasks(' not in selected_bodies and 'core_.parse_range(' not in selected_bodies
        if not report['native_authoritative_task_mirror_absent']: write_report(args.output, report); return 1
        original_header = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN+':include/swoole_static_handler.h'], text=True)
        for namespace, text in [('upstream_tasks', original), ('candidate_tasks', selected)]:
            parts = []
            if namespace == 'upstream_tasks':
                parts += [body(text, 'void StaticHandler::parse_range(')]
                parts += [body(original_header, 'const std::string &get_content_type()').replace('get_content_type()', 'StaticHandler::get_content_type()', 1)]
            else:
                parts += [body(text, 'static std::string http_range_end(')]
                parts += [body(text, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc')
            extracted.write_text('#include "tasks_oracle.h"\n#include "tasks_candidate.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN+':src/core/base.cc'], text=True)
        dependencies = tree/'dependencies.cc'; dependencies.write_text('#include "tasks_oracle.h"\n'+body(base, 'size_t sw_snprintf('))
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_tasks.cc'), str(tree/'candidate_tasks.cc'), str(dependencies), str(local/'tasks_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert all(name in symbols for name in ['swr_v2_http_tasks_prepare', 'swr_v2_http_tasks_push', 'swr_v2_http_tasks_snapshot'])
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        if args.prepare and not prepare_workload(args, tree, flags, report, 'tasks', ['tasks_candidate.h']):
            write_report(args.output, report); return 1
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
