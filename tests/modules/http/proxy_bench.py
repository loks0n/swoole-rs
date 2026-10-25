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
from gate import PIN, sha, body, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-proxy-prepare.json')
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--positive-only', action='store_true', help='Prepare only ordinary pack/authenticated workloads; excludes historical long-auth and handshake')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    archive_copy=args.binary.with_suffix('.a')
    sources_copy=args.binary.with_suffix('.sources.tar.gz')
    if any(p.exists() for p in [Path(args.output),args.binary,archive_copy,sources_copy]):parser.error('Refusing existing immutable output')
    patch = ROOT/'migration/patches/http/0001-http-helpers.patch'
    report = {'pin': PIN, 'scope': 'Actual pinned/patched proxy methods with native String/error facades; not full proxy socket/remote-service parity', 'archive_sha256': sha(args.archive), 'native_sanitizers': False, 'rust_instrumented': False, 'passed':False, 'full_gate_passed':False, 'timed':False, 'measurement_authorized':False, 'minimum_free_bytes':4*1024**3, 'profile':'positive-only' if args.positive_only else 'historical-complete', 'workloads':['pack','authenticated'] if args.positive_only else ['pack','authenticated','long-auth','handshake'], 'unrun_workloads':['long-auth','handshake'] if args.positive_only else [], 'source_capsule_scope':'Compiled selected/extracted Native sources, pinned headers, owned adapters/Rust kernels/overlays and archive copy; external compiler/SDK and unselected Cargo workspace crates are not a self-contained full production build.', 'archive_optimization':'Supplied archive; optimization/build provenance must be established by its separate exact build receipt, not inferred from bytes.'}
    with tempfile.TemporaryDirectory(prefix='swr-http-proxy-') as temp:
        tree = Path(temp)
        def guard():
            args.binary.parent.mkdir(parents=True,exist_ok=True)
            spaces={str(p):shutil.disk_usage(p).free for p in [ROOT,tree,args.binary.parent]}
            if min(spaces.values())<report['minimum_free_bytes']:
                report['blocked']={'free_bytes':spaces};write_report(args.output,report);return False
            return True
        if not guard():return 1
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'thirdparty/multipart_parser.h', 'src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        source = tree/'src/protocol/http.cc'; original = source.read_text()
        base = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/core/base.cc'], text=True)
        codec = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':src/core/base64.cc'], text=True)
        globals_source = '#include "proxy_bench_oracle.h"\nnamespace upstream_proxy { int last_error = 0; }\nnamespace candidate_proxy { int last_error = 0; }\n' + body(base, 'size_t sw_snprintf(')
        table = codec[codec.index('static char base64en[]'):codec.index('#define BASE64DE_FIRST')]
        globals_source += '\n' + table + '\n' + body(codec, 'size_t base64_encode(')
        dependencies = tree/'dependencies.cc'; dependencies.write_text(globals_source)
        apply_http_patch(tree, patch, report)
        flags = ['-std=c++14', '-DSWOOLE_RS_HTTP', '-O3', '-DNDEBUG', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/http'), '-I'+str(local)]
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        if args.positive_only:flags.append('-DSWR_HTTP_PROXY_POSITIVE')
        native_command = ['c++', *['-std=c++14' if flag == '-std=c++14' else flag for flag in flags], '-c', str(source), '-o', str(tree/'static.o')]
        if not guard():return 1
        native = run_isolated(native_command, timeout=60)
        report['native_cxx_standard'] = 'c++14'
        report['shim_cxx_standard'] = 'c++14'
        report['whole_native_translation_unit'] = {'command': native_command, 'returncode': native.returncode, 'stderr': native.stderr}
        if native.returncode: write_report(args.output, report); print(native.stderr, file=sys.stderr); return 1
        signatures = ['std::string HttpProxy::get_auth_str(', 'size_t HttpProxy::pack(', 'bool HttpProxy::handshake(']
        for namespace, text in [('upstream_proxy', original), ('candidate_proxy', source.read_text())]:
            parts = [body(text, signature) for signature in signatures]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "proxy_bench_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        command = ['c++', *flags, str(tree/'upstream_proxy.cc'), str(tree/'candidate_proxy.cc'), str(local/'proxy_bench.cc'), str(dependencies), str(args.archive.resolve()), '-lm', '-o', str(binary)]
        if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
        report['compile_command'] = command
        if not guard():return 1
        compiled = run_isolated(command, timeout=60)
        report['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
        if compiled.returncode: write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
        report['binary_sha256'] = sha(binary)
        assert all(symbol in subprocess.check_output(['nm', '-g', str(binary)], text=True) for symbol in ['swr_v1_http_proxy_pack','swr_v2_http_proxy_authorization'])
        result = run_isolated([str(binary), '--check-positive' if args.positive_only else '--check'], timeout=30); report['run'] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['outcome'] = json.loads(result.stdout.splitlines()[-1])
        if args.positive_only and (report['outcome'].get('timed') is not False or report['outcome'].get('verified') is not True):raise ValueError('Expected untimed positive verification')
        if not guard():return 1
        args.binary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, args.binary)
        shutil.copy2(args.archive, archive_copy)
        with tarfile.open(sources_copy,'w:gz') as archive:
            for path in [tree/'include',tree/'thirdparty',tree/'upstream_proxy.cc',tree/'candidate_proxy.cc',dependencies,source]:archive.add(path,arcname='native/'+path.name)
            for path in [local/'proxy_bench.cc',local/'proxy_bench_oracle.h',Path(__file__)]:archive.add(path,arcname='adapter/'+path.name)
            for path in [ROOT/'native/http',ROOT/'crates/http',ROOT/'crates/base64',ROOT/'crates/ffi',ROOT/'migration/patches/http',ROOT/'Cargo.toml',ROOT/'Cargo.lock']:archive.add(path,arcname='repo/'+str(path.relative_to(ROOT)))
        if sha(args.binary)!=report['binary_sha256'] or sha(archive_copy)!=report['archive_sha256']:raise ValueError('Prepared copy identity differs')
        report['passed']=True
        report['prepared_binary'] = str(args.binary.resolve())
        write_report(args.output, report); print(json.dumps(report['outcome']))
    return 0
if __name__ == '__main__': sys.exit(main())
