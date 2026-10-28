#!/usr/bin/env python3
"""Actual original/patched protocol TU comparison. No network listener or timing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
from tools.native_core import library_identity, verify_loader_output, test_outcome


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Matching configured pinned native tree')
    parser.add_argument('--reference', type=Path, required=True, help='Pinned Git reference checkout, read-only')
    parser.add_argument('--library', type=Path, required=True, help='Existing unselected native full-core library')
    parser.add_argument('--openssl', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--command-timeout', type=int, default=90, help='Explicit bounded per-command correctness deadline, 1..300 seconds')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--crypto-allocation', action='store_true', help='Supported OpenSSL allocator-hook failures through actual selected setup operation')
    parser.add_argument('--crypto-operation', choices=['client-ca','dhparam','curve','dtls-init'], default='client-ca', help='Actual original method for --crypto-allocation; default unchanged')
    modes.add_argument('--allocation', action='store_true', help='Controlled native C++new failures and lazy warning allocation profile')
    modes.add_argument('--benchmark-check', action='store_true', help='Prepare optimized actual-TU workloads, execute checks only; never measure')
    modes.add_argument('--peers', action='store_true', help='MemoryBIO TLS verification/ALPN/shutdown and actual DTLS listen fixture')
    parser.add_argument('--gtest-prefix', type=Path, help='Existing GoogleTest prefix for unchanged ssl.* originals')
    parser.add_argument('--archive', type=Path, help='Published selected Rust archive; otherwise compile owned source')
    parser.add_argument('--sanitize', action='store_true', help='Native ASan/UBSan only, Rust instrumented separately')
    args = parser.parse_args()
    if args.crypto_operation!='client-ca' and not args.crypto_allocation:
        parser.error('--crypto-operation requires --crypto-allocation')
    if not 1 <= args.command_timeout <= 300:
        parser.error('--command-timeout must be between1 and300 seconds')
    if args.benchmark_check and (args.peers or args.sanitize or args.gtest_prefix):
        parser.error('--benchmark-check requires unsanitized optimized module-only compilation')
    if args.benchmark_check and not args.archive:
        parser.error('--benchmark-check requires an actual selected FFI archive')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    attempt = args.output.parent.resolve() / ('tls-' + uuid.uuid4().hex);attempt.mkdir()
    driver=ROOT/'tests/modules/tls'/('crypto_allocation.cc' if args.crypto_allocation else 'allocation.cc' if args.allocation else 'benchmark.cc' if args.benchmark_check else 'peers.cc' if args.peers else 'driver.cc')
    source = args.source.resolve();library = args.library.resolve();openssl = args.openssl.resolve()
    report = dict(passed=False, utc=datetime.now(timezone.utc).isoformat(), attempt=str(attempt),
        commands=[], command_timeout_seconds=args.command_timeout, native_sanitizers=args.sanitize, rust_sanitizers=False,
        scope='Complete actual protocol TUs, initialized SSLContext/config masks and actual DTLS BIO callbacks; no handshake/PHP/network/performance claim.',
        excluded=['Original ssl.password uninitialized scalar fields: separate original gate',
            'Negative BIO read length and append/OOM/overflow original undefined inputs',
            'Cookie uninitialized/alignment domain unchanged native', 'Optional libraries/platforms not this actual configuration'])
    env = os.environ.copy()
    for k in ['LD_PRELOAD', 'LD_AUDIT', 'DYLD_INSERT_LIBRARIES']:
        if env.get(k): raise ValueError('Injected library environment unsupported')
    report['removed_tracing'] = {k: env.pop(k) for k in list(env) if k.startswith(('LD_DEBUG','LD_TRACE_','DYLD_PRINT_'))}
    env['GTEST_COLOR'] = 'no'
    system = platform.system();selection = 'DYLD_LIBRARY_PATH' if system == 'Darwin' else 'LD_LIBRARY_PATH'
    env[selection] = str(library.parent)
    env['SWR_TLS_NATIVE_LIBRARY'] = str(library)
    env['SWR_TLS_REFERENCE'] = str(args.reference.resolve())
    env['SWR_TLS_CRYPTO_OPERATION'] = args.crypto_operation
    if args.sanitize:
        env.update(ASAN_OPTIONS='abort_on_error=1:detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    def run(command, cwd=attempt, extra=None):
        idx = len(report['commands']);log = attempt / f'{idx:02d}.log'
        try:
            result = run_isolated(list(map(str,command)), cwd=cwd, timeout=args.command_timeout, env={**env, **(extra or {})})
        except subprocess.TimeoutExpired as error:
            def decode(value): return value.decode(errors='replace') if isinstance(value,bytes) else value or ''
            log.write_text(decode(error.stdout)+decode(error.stderr))
            report['commands'].append(dict(argv=list(map(str,command)),returncode=124,timed_out=True,log=str(log)))
            raise RuntimeError('Command exceeded explicit deadline; partial output retained: '+str(log)) from error
        log.write_text(result.stdout+result.stderr)
        report['commands'].append(dict(argv=list(map(str,command)), returncode=result.returncode, log=str(log)))
        if result.returncode: raise RuntimeError('Command failed: ' + str(log))
        return result
    def crypto_snapshot(output):
        pattern = (r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*lib(?:ssl|crypto)[^/]*\.dylib)\s*$'
                   if system == 'Darwin' else r'^\s*lib(?:ssl|crypto)[^ ]* => (/[^ ]+) \(0x[0-9a-fA-F]+\)')
        paths = sorted(set(re.findall(pattern, output, re.M)))
        files = [library_identity(p) for p in paths if Path(p).is_file()]
        configured = [row for row in files if Path(row['resolved_path']).is_relative_to(openssl)]
        if not any(Path(row['path']).name.startswith('libssl') for row in configured) or not any(Path(row['path']).name.startswith('libcrypto') for row in configured):
            raise ValueError('Missing/foreign actual configured crypto library resolution')
        return {'files': files, 'unhashable_shared_cache_paths': [p for p in paths if not Path(p).is_file()]}

    def crypto_unchanged(snapshot):
        if any(library_identity(row['path']) != row for row in snapshot['files']):
            raise ValueError('Actual loaded crypto library changed during execution')

    def verify_calls(executable, selected):
        nm=run(['nm','-g',executable]).stdout
        disassembly=run(['otool','-tvV',executable] if system=='Darwin' else ['objdump','-d','-C',executable]).stdout
        names=['init','error','context_create','set_capath','set_ciphers','set_client_certificate','set_ecdh_curve','set_dhparam','read','control','listen']
        calls={name:bool(re.search(r'\b(?:bl|callq?|b|jmpq?)\s+[^\n]*\b_?swr_v1_tls_'+name+r'\b',disassembly)) for name in names}
        definitions={name:bool(re.search(r'\b[Tt] _?swr_v1_tls_'+name+r'\s*$',nm,re.M)) for name in names}
        if selected and (not all(calls.values()) or not all(definitions.values())):
            raise ValueError('Selected caller/binary proof missing: '+repr(calls)+' '+repr(definitions))
        if not selected and ('swr_v1_tls_' in nm or any(calls.values())):
            raise ValueError('Original comparator unexpectedly contains TLS Rust symbols')
        return {'call_instructions':calls,'definitions':definitions}

    try:
        if args.crypto_allocation:
            report['crypto_operation']=args.crypto_operation
            report['scope']='Supported OpenSSL allocator-hook single-failure sweep through actual native '+args.crypto_operation+' method; no PHP/system OOM, alternate crypto library or performance claim'
            report['excluded'].append('Original null ERR_reason_error_string argument to native %s formatting is a platform observation, not portable defined-input or safety proof')
        if args.allocation:
            report['scope']='Controlled replaceable C++ operator-new failure/count/size traces through actual native warning formatting; no malloc/system/PHP OOM or Rust-allocation failure claim'
        if args.benchmark_check:
            report['scope']='Optimized actual protocol TUs and six fixed full-context/DTLS BIO workloads; check-only, no driver timing-clock calls or measurements in this preparation'
            report['measurement_executed']=False
        if args.peers:
            report['scope']='Complete original/patched protocol TUs, callback-driven MemoryBIO TLS1.2/1.3 trust/hostname/ALPN/data/shutdown and native DTLS listen/cookie/datagram socketpair peer; no IP Socket/PHP/packetloss/cancel/performance claim'
        expected = library_identity(library);report['native_library_before'] = expected
        manifest = ROOT / 'migration/patches/tls/manifest.json'
        m = json.loads(manifest.read_text());pin = m['upstream_commit'];report['upstream_commit'] = pin
        original = attempt/'original';patched=attempt/'patched'
        for folder in [original,patched]: (folder/'src/protocol').mkdir(parents=True)
        for name in ['ssl.cc','dtls.cc']:
            # Pinned Git content, never mutate or trust arbitrary scratch source.
            result = run(['git','-C',args.reference.resolve(),'show',pin+':src/protocol/'+name])
            for folder in [original,patched]: (folder/'src/protocol'/name).write_text(result.stdout)
        # git apply otherwise silently filters paths below an enclosing worktree.
        # Give this disposable tree its own explicit Git root, then verify effects.
        run(['git','init','--quiet',patched])
        top=run(['git','-C',patched,'rev-parse','--show-toplevel']).stdout.strip()
        if Path(top).resolve()!=patched.resolve(): raise ValueError('Foreign patch worktree')
        for p in m['patches']:
            path=ROOT/'migration/patches/tls'/p['path']
            if digest(path)!=p['sha256']: raise ValueError('Patch hash mismatch')
            run(['git','apply','--check',path],cwd=patched)
            run(['git','apply',path],cwd=patched)
        for name, required in [('ssl.cc',['context_create','set_capath']),('dtls.cc',['read','control','listen'])]:
            old=original/'src/protocol'/name;new=patched/'src/protocol'/name
            if old.read_bytes()==new.read_bytes() or any('swr_v1_tls_'+fn+'(' not in new.read_text() for fn in required):
                raise ValueError('Overlay skipped or missing actual caller: '+name)

        archive=args.archive.resolve() if args.archive else attempt/'libtls.a'
        if not args.archive: run(['rustc','--edition=2024','--crate-type','staticlib','-C','opt-level=2',ROOT/'crates/tls/src/lib.rs','-o',archive])
        # Mac two-level DSO binding otherwise leaves Socket::ssl_create using the
        # DSO's separate ex_data authority while these actual protocol TUs own
        # another. Compile the unchanged pinned real caller in both comparators;
        # no protected source patch or stub and no full native-world rebuild.
        # Linux binds flat: the executable's protocol TUs already interpose the DSO's, and a second
        # copy of socket.cc there is an ODR violation that ASan aborts on.
        socket_sources=[]
        if sys.platform=='darwin' and (args.peers or (args.crypto_allocation and args.crypto_operation=='dtls-init')):
            socket_source=attempt/'native-socket.cc'
            socket_source.write_text(run(['git','-C',args.reference.resolve(),'show',pin+':src/network/socket.cc']).stdout)
            socket_sources=[socket_source]
            for name in ['swoole.h','swoole_ssl.h','swoole_dtls.h','swoole_socket.h']:
                header=source/'include'/name
                pinned=run(['git','-C',args.reference.resolve(),'show',pin+':include/'+name]).stdout.encode()
                if hashlib.sha256(pinned).hexdigest()!=digest(header):
                    raise ValueError('Native Socket caller public header differs from pin: '+name)
            report['native_socket_caller']={'source':str(socket_source),
                'pin':pin,'upstream_path':'src/network/socket.cc','backend':'unchanged native caller in both engines',
                'purpose':'One protocol/ex_data authority with actual native Socket caller; full DSO supplies remaining dependencies',
                'excluded':'No selected M15 Socket policy or full integrated PHP coverage claim'}
        outputs={}
        report['original_google_tests'] = {'status': 'NOT_RUN'}
        if args.gtest_prefix:
            original_tests = attempt/'original-ssl.cpp'
            original_tests.write_text(run(['git','-C',args.reference.resolve(),'show',pin+':core-tests/src/protocol/ssl.cpp']).stdout)
            report['original_google_tests'] = {}
            env['SWR_TLS_REFERENCE'] = str(args.reference.resolve())
        for label,folder in [('original',original),('rust',patched)]:
            executable=folder/'driver'
            flags=['-std=c++14','-O2','-DHAVE_CONFIG_H','-I'+str(source),'-I'+str(source/'include'),'-I'+str(openssl/'include')]
            if args.sanitize: flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g']
            if label=='rust': flags+=['-DSWOOLE_RS_TLS','-I'+str(ROOT/'native/tls')]
            link=['-L'+str(openssl/'lib'),'-lssl','-lcrypto',str(library),'-Wl,-rpath,'+str(library.parent),'-pthread']
            run(['c++',*flags,driver,folder/'src/protocol/ssl.cc',folder/'src/protocol/dtls.cc',*socket_sources,*([archive]if label=='rust'else []),*link,'-o',executable])
            report[label+'_caller_proof']=verify_calls(executable,label=='rust')
            if args.peers:
                binding=json.loads(run([executable,'--callback-binding']).stdout)
                report[label+'_callback_binding']=binding
                if not binding.get('supported'):
                    raise ValueError('Callback binding witness unsupported by this actual SDK; no PASS claim')
                expected_binding=label=='original'
                if binding['has_callback_ctrl']!=expected_binding or binding['callback_is_public_dispatcher']!=expected_binding:
                    raise ValueError('Actual callback registration differs from declared original/corrected contract')
                report['deliberate_corrections']=[{'boundary':'BIO callback-control method registration',
                    'original':'Public OpenSSL dispatcher installed as its own method leaf',
                    'selected':'Unset unsupported leaf; SDK owns error behavior',
                    'validation':'Typed pointer identity only; callback-control operation and liveness NOT_RUN',
                    'scope':'Deliberate native contract correction, not Rust conversion or original callback-control parity'}]
            if args.gtest_prefix:
                gtest=args.gtest_prefix.resolve();test_binary=folder/'original-tests'
                run(['c++',*flags,'-I'+str(source/'core-tests/include'),'-I'+str(gtest/'include'),original_tests,
                     ROOT/'tests/modules/tls/original_main.cc',folder/'src/protocol/ssl.cc',folder/'src/protocol/dtls.cc',
                     *([archive]if label=='rust'else []),gtest/'lib/libgtest.a',*link,'-o',test_binary])
                report[label+'_original_caller_proof']=verify_calls(test_binary,label=='rust')
                setting='DYLD_PRINT_LIBRARIES' if system=='Darwin' else 'LD_TRACE_LOADED_OBJECTS'
                probe=run([test_binary,'--gtest_list_tests'],extra={setting:'1'})
                crypto=crypto_snapshot(probe.stdout+probe.stderr)
                report[label+'_original_loader']=verify_loader_output(probe.stdout+probe.stderr,expected,system)
                report[label+'_original_crypto_before']=crypto
                report['original_google_tests'][label]={}
                for case in ['destroy','get_error','password']:
                    xml=folder/(case+'.xml')
                    if xml.exists(): raise ValueError('Stale original XML before invocation')
                    result=run([test_binary,'--gtest_filter=ssl.'+case,'--gtest_output=xml:'+str(xml)])
                    outcome=test_outcome(xml,'ssl.'+case,result.returncode)
                    if outcome['status']!='passed' or '[ RUN      ] ssl.'+case not in result.stdout or '[       OK ] ssl.'+case not in result.stdout:
                        raise ValueError('Original execution not exactly RUN/completed/PASS: '+repr(outcome))
                    crypto_unchanged(crypto)
                    report['original_google_tests'][label][case]={**outcome,'xml':str(xml)}
            setting='DYLD_PRINT_LIBRARIES'if system=='Darwin'else'LD_TRACE_LOADED_OBJECTS'
            probe=run([executable,'--identify'],extra={setting:'1'})
            report[label+'_loader']=verify_loader_output(probe.stdout+probe.stderr,expected,system)
            crypto=crypto_snapshot(probe.stdout+probe.stderr)
            report[label+'_crypto_before']=crypto
            result=run([executable]);outputs[label]=result.stdout
            crypto_unchanged(crypto)
            (attempt/(label+'.tsv')).write_text(result.stdout)
            report[label+'_stderr']=result.stderr
        # Preserve exact warning payload/count, normalizing only native logger wall-clock/PID prefix.
        # Raw stdout above remains immutable; it is expected to differ between processes.
        normalized = {k: re.sub(r'^\[[^\]\n]+\]\tWARNING\t', 'WARNING\t', v, flags=re.M)
                      for k, v in outputs.items()}
        report['warning_prefix_normalization'] = 'Only native logger [timestamp PID] prefix; exact payload/count and all data rows compared, raw outputs retained'
        report['unknown_warning_counts'] = {k: v.count('WARNING\tdtls::BIO_ctrl(): unknown cmd: -12345') for k,v in normalized.items()}
        if not args.peers and not args.allocation and not args.crypto_allocation and not args.benchmark_check and set(report['unknown_warning_counts'].values()) != {4}: raise ValueError('Missing/extra expected unknown-command warnings')
        if normalized['original']!=normalized['rust']: raise ValueError('Actual TU result mismatch; both outputs retained')
        report['native_library_after']=library_identity(library)
        if report['native_library_after']!=expected: raise ValueError('Native library changed')
        if args.benchmark_check:
            report['prepared_commands']={label:[str(attempt/('patched' if label=='rust' else label)/'driver'),'--measure'] for label in ['original','rust']}
            report['check_commands']={label:[str(attempt/('patched' if label=='rust' else label)/'driver'),'--check'] for label in ['original','rust']}
            report['fixed_workloads']=[dict(name=parts[0],operations=int(parts[1]),checksum=int(parts[2])) for parts in map(str.split, outputs['original'].splitlines())]
            if len(report['fixed_workloads'])!=6: raise ValueError('Expected exactly six checked optimized workloads')
        report.update(passed=True, rows=len(outputs['original'].splitlines()))
    except Exception as error:
        report['error']=str(error)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k)for k in ['passed','rows','error','attempt']}))
    return int(not report['passed'])

if __name__=='__main__': sys.exit(main())
