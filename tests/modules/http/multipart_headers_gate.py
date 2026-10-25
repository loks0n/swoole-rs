#!/usr/bin/env python3
"""Multipart header filename policy through actual native callbacks and file-operation facades."""
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
    parser.add_argument('--positive-only', action='store_true', help='Only ordinary headers and successful upload acquisition; excludes fault/reentry profiles')
    parser.add_argument('--output', default='target/reports/http-multipart-headers.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched multipart header field/value and cookie bodies; native append/file facades, not full parser/PHP parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False, 'positive_only':args.positive_only, 'full_gate_passed':False, 'unrun_profiles':['allocation/stdio failure, seeded/partial state, malformed/random input, reentry/lifetime and actual IO/PHP'] if args.positive_only else []}
    with tempfile.TemporaryDirectory(prefix='swr-http-multipart-headers-') as temp:
        tree = Path(temp)
        if not prepare_archive(args, tree, report):
            write_report(args.output, report)
            return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/protocol/http.cc', 'thirdparty/multipart_parser.h'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/protocol/http.cc'; original = source.read_text()
        apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-DSWOOLE_RS_HTTP', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-I'+str(tree), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        for namespace, text in [('upstream_multipart_headers', original), ('candidate_multipart_headers', source.read_text())]:
            extracted = tree/(namespace+'.inc')
            parts = [body(text,'void parse_cookie('),body(text,'static int multipart_on_header_field('),body(text,'static int multipart_on_header_value(')]
            if 'static int http_multipart_emit(' in text: parts.insert(0,body(text,'static int http_multipart_emit('))
            if 'static auto http_cookie_scratch(' in text: parts.insert(0,body(text,'static auto http_cookie_scratch(const char *at, size_t length) -> String * {'))
            extracted.write_text('namespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(local/'multipart_headers_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert 'swr_v1_http_multipart_filename' in symbols and 'swr_v2_http_multipart_upload' in symbols
        result = run_isolated([str(binary), *(['--positive-only'] if args.positive_only else [])], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
