#!/usr/bin/env python3
"""Actual StaticHandlerV2 storage/index/page callers with normal scan/storage facades."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_static_header, prepare_index_buffer, prepare_workload, add_archive_arguments, prepare_archive, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--prepare', type=Path, help='Create a new immutable optimized directory workload artifact; run untimed preflight only')
    parser.add_argument('--output', default='target/reports/http-directory-v2.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    if args.prepare and args.rust_sanitize: parser.error('--prepare requires an optimized uninstrumented archive')
    if args.prepare and args.prepare.exists(): parser.error('--prepare destination must not already exist')
    patch = ROOT/'migration/patches/http/0002-static-ranges.patch'
    report = {'pin': PIN, 'scope': 'Actual legacy scan/index/page bodies versus actual typed V2 class/functions and real Rust directory store; normal counted scan/String/Server facades, not full IO/PHP/lifetime parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False, 'full_gate_passed': False, 'unrun_profiles': ['allocation failures', 'filesystem errors', 'callback/reentry/process/response lifetime', 'legacy direct collection compatibility', 'performance']}

    with tempfile.TemporaryDirectory(prefix='swr-http-directory-') as temp:
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
        prepare_index_buffer(tree, report)
        header = (ROOT/'native/http/swoole_rs_http_static_v2.h').read_text()
        typed = body(header, 'class StaticHandlerV2')
        (tree/'directory_candidate.h').write_text('#pragma once\nnamespace candidate_directory {\n'+typed+';\n}\n')
        selected = source.read_text()
        signatures = ['StaticHandlerV2::StaticHandlerV2(', 'StaticHandlerV2::~StaticHandlerV2(', 'bool StaticHandlerV2::get_dir_files(', 'bool StaticHandlerV2::try_serve_index_file(', 'static void append_directory_part(', 'size_t StaticHandlerV2::make_index_page(']
        selected_bodies = typed + '\n'.join(body(selected, signature) for signature in signatures)
        report['native_directory_mirror_absent'] = '.dir_files' not in selected_bodies and 'core_.get_dir_files(' not in selected_bodies
        if not report['native_directory_mirror_absent']: write_report(args.output, report); return 1
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN+':src/core/base.cc'], text=True)
        for namespace in ['upstream_directory','candidate_directory']:
            parts = [body(base, 'std::string intersection(')]
            if namespace == 'upstream_directory':
                parts += [body(original, signature) for signature in ['bool StaticHandler::get_dir_files(', 'bool StaticHandler::try_serve_index_file(', 'size_t StaticHandler::make_index_page(']]
            else:
                parts += [body(selected, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc')
            extracted.write_text('#include "directory_oracle.h"\n#include "directory_candidate.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        dependencies = tree/'dependencies.cc'
        dependencies.write_text('#include "directory_oracle.h"\n'+body(base, 'size_t sw_snprintf('))
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_directory.cc'), str(tree/'candidate_directory.cc'), str(dependencies), str(local/'directory_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert 'swr_v2_http_directory_scan_append' in symbols and 'swr_v2_http_directory_scan_finish' in symbols
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        if args.prepare and not prepare_workload(args, tree, flags, report, 'directory', ['directory_candidate.h','index_buffer.h']):
            write_report(args.output, report); return 1
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
