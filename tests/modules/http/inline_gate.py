#!/usr/bin/env python3
"""Actual StaticHandler inline method, allocation/RNG/reference/path checks."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, add_archive_arguments, prepare_archive, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--output', default='target/reports/http-inline.json')
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    patches = [ROOT/'migration/patches/http'/name for name in ['0002-static-ranges.patch', '0003-static-inline.patch']]
    report = {'pin': PIN, 'scope': 'Actual pinned/patched StaticHandler inline bodies, allocation failures and native RNG/MIME facades; not filesystem/PHP/server parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-inline-') as temp:
        tree = Path(temp)
        if not prepare_archive(args, tree, report):
            write_report(args.output, report)
            return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'include/swoole_static_handler.h'; original = source.read_text()
        for patch in patches:
            apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(tree/'src/server/static_handler.cc'), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        signatures = ['bool catch_error(', 'const std::string &get_boundary(', 'const std::string &get_content_type(', 'bool is_absolute_path(', 'bool is_located_in_document_root(']
        for namespace, text in [('original_inline', original), ('candidate_inline', source.read_text())]:
            parts = []
            for signature in signatures:
                method = body(text, signature)
                name = signature.split('(')[0].split()[-1].lstrip('&')
                method = method.replace(name+'(', 'StaticHandler::'+name+'(', 1)
                parts.append(method)
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "inline_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'original_inline.cc'), str(tree/'candidate_inline.cc'), str(local/'inline_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert all(name in symbols for name in ['swr_v1_http_static_boundary', 'swr_v1_http_static_content_type', 'swr_v1_http_static_path_check', 'swr_v1_http_static_catch'])
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
