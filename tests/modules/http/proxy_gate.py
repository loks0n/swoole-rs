#!/usr/bin/env python3
"""Differential actual CONNECT serialization and handshake bodies; native allocation remains outside Rust."""
import argparse
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_http_patch, add_archive_arguments, prepare_archive
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--auth-positive-only', action='store_true', help='Only 25 bounded credentials and ordinary CONNECT prefix controls; excludes oversized credentials and all handshake profiles')
    parser.add_argument('--output', default='target/reports/http-proxy.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    if Path(args.output).exists(): parser.error('Refusing an existing receipt')
    patch = ROOT/'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched proxy methods with native String/error facades; not full proxy socket/remote-service parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False, 'full_gate_passed': False, 'profile': 'auth-positive-only' if args.auth_positive_only else 'original-complete', 'minimum_free_bytes': 4*1024**3, 'unrun_profiles': ['Full original proxy corpus, oversized/fault/allocation/lifetime/handshake profiles'] if args.auth_positive_only else []}
    with tempfile.TemporaryDirectory(prefix='swr-http-proxy-') as temp:
        tree = Path(temp)
        def guard():
            free = shutil.disk_usage(tree).free
            if free < report['minimum_free_bytes']:
                report['blocked'] = {'free_bytes': free}; write_report(args.output, report); return False
            return True
        if not guard(): return 1
        if not prepare_archive(args, tree, report): write_report(args.output, report); return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'thirdparty/multipart_parser.h', 'src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/protocol/http.cc'; original = source.read_text()
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/core/base.cc'], text=True)
        codec = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/core/base64.cc'], text=True)
        globals_source = '#include "proxy_oracle.h"\n' + body(base, 'size_t sw_snprintf(')
        table = codec[codec.index('static char base64en[]'):codec.index('#define BASE64DE_FIRST')]
        globals_source += '\n' + table + '\n' + body(codec, 'size_t base64_encode(')
        dependencies = tree/'dependencies.cc'; dependencies.write_text(globals_source)
        apply_http_patch(tree, patch, report)
        flags = ['-std=c++17', '-DSWOOLE_RS_HTTP', '-O1', '-g', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), '-I'+str(local), '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++17' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        if not guard(): return 1
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++17'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        signatures = ['std::string HttpProxy::get_auth_str(', 'size_t HttpProxy::pack(', 'bool HttpProxy::handshake(']
        for namespace, text in [('upstream_proxy', original), ('candidate_proxy', source.read_text())]:
            parts = [body(text, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "proxy_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_proxy.cc'), str(tree/'candidate_proxy.cc'), str(local/'proxy_gate.cc'), str(dependencies), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command
        if not guard(): return 1
        compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        assert 'swr_v1_http_proxy_pack' in subprocess.check_output(['nm', '-g', str(binary)], text=True)
        result = run_isolated([str(binary)] + (['--auth-positive-only'] if args.auth_positive_only else []), timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1]); report['passed'] = True
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
