#!/usr/bin/env python3
"""Actual HTTP dispatch/index/proxy creation/status boundary checks."""
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
    parser.add_argument('--output', default='target/reports/http-dispatch.json')
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    patches = [ROOT/'migration/patches/http'/name for name in ['0001-http-helpers.patch', '0002-static-ranges.patch', '0003-static-inline.patch']]
    report = {'pin': PIN, 'scope': 'Actual pinned/patched HTTP route/index/proxy-init/status bodies with deterministic native execution facades; not socket/PHP/full class allocation parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-dispatch-') as temp:
        tree = Path(temp)
        if not prepare_archive(args, tree, report):
            write_report(args.output, report)
            return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'thirdparty/multipart_parser.h', 'src/protocol/http.cc', 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        paths = ['src/protocol/http.cc', 'src/server/static_handler.cc']
        originals = {name: (tree/name).read_text() for name in paths}
        for patch in patches:
            apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        report['whole_native_translation_units'] = {}
        for index, name in enumerate(paths):
            command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(tree/name), '-o', str(tree/f'native{index}.o')]
            result = run_isolated(command, timeout=60)
            report['whole_native_translation_units'][name] = {'command': command, 'returncode': result.returncode, 'stderr': result.stderr}
            if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        protocol_signatures = ['HttpProxy *HttpProxy::create(', 'const char *get_status_message(', 'ssize_t get_package_length(', 'uint8_t get_package_length_size(', 'int dispatch_frame(']
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN+':src/core/base.cc'], text=True)
        dependencies = tree/'dependencies.cc'; dependencies.write_text('#include "dispatch_oracle.h"\n' + body(base, 'size_t sw_snprintf('))
        for namespace, texts in [('upstream_dispatch', originals), ('candidate_dispatch', {name: (tree/name).read_text() for name in paths})]:
            parts = ['static thread_local char http_status_message[128];', body(base, 'std::string intersection(')]
            parts += [body(texts[paths[0]], signature) for signature in protocol_signatures]
            parts += [body(texts[paths[1]], 'bool StaticHandler::try_serve_index_file(')]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "dispatch_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_dispatch.cc'), str(tree/'candidate_dispatch.cc'), str(local/'dispatch_gate.cc'), str(dependencies), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command; compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
        assert all(name in symbols for name in ['swr_v1_http_transport_route', 'swr_v1_http_index_file', 'swr_v1_http_unknown_status', 'swr_v1_http_proxy_auth_enabled'])
        result = run_isolated([str(binary)], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
