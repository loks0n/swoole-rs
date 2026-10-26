#!/usr/bin/env python3
"""Actual mature multipart parser with pinned callbacks, Rust policy and real private upload files."""
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
    parser.add_argument('--output', default='target/reports/http-multipart-parser.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Actual mature parser and seven pinned/patched callbacks with real private stdio/upload files and incremental bodies; storage/error facades, not PHP parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-multipart-parser-') as temp:
        tree = Path(temp)
        if not prepare_archive(args, tree, report):
            write_report(args.output, report)
            return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/protocol/http.cc', 'thirdparty/multipart_parser.h', 'thirdparty/multipart_parser.c'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/protocol/http.cc'; original = source.read_text()
        apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-I'+str(tree), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        for namespace, text in [('upstream_multipart_parser', original), ('candidate_multipart_parser', source.read_text())]:
            extracted = tree/(namespace+'.inc')
            parts = [body(text,'void parse_cookie(')] + [body(text,'static int '+name+'(') for name in ['multipart_on_header_field','multipart_on_header_value','multipart_on_data','multipart_on_header_complete','multipart_on_data_end','multipart_on_part_begin','multipart_on_body_end']] + [body(text,'bool Request::parse_multipart_data(')]
            start=text.index('static constexpr multipart_parser_settings mt_parser_settings');end=text.index('};',start)+2;parts.append(text[start:end])
            if 'static int http_multipart_emit(' in text: parts.insert(0,body(text,'static int http_multipart_emit('))
            if 'static auto http_cookie_scratch(' in text: parts.insert(0,body(text,'static auto http_cookie_scratch(const char *at, size_t length) -> String * {'))
            extracted.write_text('namespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        parser_source=tree/'thirdparty/multipart_parser.c'
        parser_object=tree/'multipart_parser.o'
        parser_compile=['cc','-std=c11','-include','sys/types.h','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-c',str(parser_source),'-o',str(parser_object)]
        report['parser_compile_command']=parser_compile
        parsed=run_isolated(parser_compile,timeout=60)
        report['parser_compile']={'returncode':parsed.returncode,'stderr':parsed.stderr}
        if parsed.returncode: write_report(args.output,report);print(parsed.stderr,file=sys.stderr);return 1
        binary = tree/'gate'
        command = ['c++', *flags, str(local/'multipart_parser_gate.cc'), str(parser_object), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        assert 'swr_v1_http_multipart_filename' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
