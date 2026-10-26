#!/usr/bin/env python3
"""Prepare an optimized actual-filesystem path consumer; execute correctness only."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-path-prepare.json')
    parser.add_argument('--binary', type=Path, required=True)
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    patches = [ROOT/'migration/patches/http'/name for name in ['0002-static-ranges.patch', '0003-static-inline.patch']]
    report = {'pin': PIN, 'scope': 'Actual pinned/patched try_serve/get_absolute_path and relevant inline bodies, real POSIX filesystem and pinned MIME implementation; minimal Server/Handler ABI shim, not full app/IO parity', 'native_sanitizers': False, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-path-') as temp:
        tree = Path(temp)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc', 'src/protocol/mime_type.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/server/static_handler.cc'; original = source.read_text()
        header = tree/'include/swoole_static_handler.h'; original_header = header.read_text()
        for patch in patches:
            apply_http_patch(tree, patch, report)
        flags = ['-std=c++14', '-O3', '-DNDEBUG', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http'), '-I'+str(local)]
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++14' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++14'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        protocol = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/protocol/http.cc'], text=True)
        for namespace, text, inline in [('upstream_path', original, original_header), ('candidate_path', source.read_text(), header.read_text())]:
            parts = [body(protocol, 'static int url_htoi('),body(protocol, 'size_t url_decode('),body(text, 'bool StaticHandler::get_absolute_path('),body(text, 'bool StaticHandler::try_serve(')]
            for member in ['catch_error', 'is_absolute_path', 'is_located_in_document_root']:
                parts.append(body(inline, 'bool '+member+'(').replace(member+'(', 'StaticHandler::'+member+'(', 1))
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "path_bench_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_path.cc'), str(tree/'candidate_path.cc'), str(local/'path_bench.cc'), str(tree/'src/protocol/mime_type.cc'), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        assert 'swr_v1_http_static_path' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        result = run_isolated([str(binary), '--check'], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        args.binary.parent.mkdir(parents=True, exist_ok=True)
        __import__('shutil').copy2(binary, args.binary)
        report['prepared_binary'] = str(args.binary.resolve())
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
