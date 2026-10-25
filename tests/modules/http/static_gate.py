#!/usr/bin/env python3
"""Actual static response method comparison with counted native IO/date/MIME facades."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_static_header, add_archive_arguments, prepare_archive, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--positive-only', action='store_true', help='Normal response controls only; injected failures, callback mutations and extreme integer profiles remain unrun')
    parser.add_argument('--output', default='target/reports/http-static.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/http/0002-static-ranges.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched static response method with counted native facades; not filesystem/socket/PHP parity', 'positive_only': args.positive_only, 'full_gate_passed': False, 'unrun_profiles': ['injected send exceptions/errors', 'callback metadata mutations', 'extreme integer values'] if args.positive_only else [], 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-static-') as temp:
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
        flags = ['-std=c++17', '-DSWOOLE_RS_HTTP', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/core/base.cc'], text=True)
        dependencies = tree/'dependencies.cc'; dependencies.write_text('#include "static_oracle.h"\n' + body(base, 'size_t sw_snprintf('))
        for namespace, text in [('upstream_static', original), ('candidate_static', source.read_text())]:
            parts = []
            if 'static swr_v1_http_proxy_text static_header_text(' in text:
                parts += [body(text, 'static swr_v1_http_proxy_text static_header_text('), body(text, 'static size_t encode_static_headers(')]
            if 'static bool select_static_handler_impl(' in text:
                view = ROOT/'native/http/swoole_rs_http_request_view.h'
                parts.append('namespace http_server { template<class T>\n' + body(view.read_text(), 'class LegacyRequestView {') + '; }')
                parts.append('template<class RequestView>\n' + body(text, 'static bool select_static_handler_impl('))
            parts.append(body(text, 'bool Server::select_static_handler('))
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "static_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_static.cc'), str(tree/'candidate_static.cc'), str(dependencies), str(local/'static_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert 'swr_v1_http_static_headers' in symbols and 'swr_v1_http_static_body' in symbols and 'swr_v1_http_static_select' in symbols
        result = run_isolated([str(binary)] + (['--positive-only'] if args.positive_only else []), timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True; report['full_gate_passed'] = not args.positive_only
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
