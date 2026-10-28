#!/usr/bin/env python3
"""Conditional-date comparison using actual libc calendar calls and extracted native callers."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_static_header, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-conditionals.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/http/0002-static-ranges.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched conditional callers with libc calendar calls; defined inputs/errno/call order, not PHP/server parity', 'native_sanitizers': True, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-conditional-') as temp:
        tree = Path(temp)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/server/static_handler.cc'; original = source.read_text()
        apply_http_patch(tree, patch, report)
        apply_static_header(tree, report)
        flags = ['-std=c++17', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        for namespace, text in [('upstream_conditional', original), ('candidate_conditional', source.read_text())]:
            extracted = tree/(namespace+'.cc')
            # Keep the actual generic declaration used by legacy and V2 callers.
            prefix = 'template<typename Handler>\n' if 'template<typename Handler>\nstatic bool conditional_file_date(' in text else ''
            parts = ([prefix + body(text, 'static bool conditional_file_date(')] if namespace == 'candidate_conditional' else []) + [body(text, 'bool StaticHandler::is_modified('), body(text, 'bool StaticHandler::is_modified_range(')]
            # The selected handler names its server serv_; the facade's is serv.
            extracted.write_text('#include "conditional_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts).replace('serv_,','serv,')+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_conditional.cc'), str(tree/'candidate_conditional.cc'), str(local/'conditional_gate.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        assert 'swr_v1_http_conditional' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
