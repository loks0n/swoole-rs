#!/usr/bin/env python3
"""Instrument actual reactor Rust instructions; native/PHP sanitizer scopes stay distinct."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated
from tools.build_upstream import require_build_space


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dependency_target(root, out, compiler, env, cache_root=None):
    """Same-owner Cargo intermediates only; final ASan artifacts never live here."""
    manifests = ['Cargo.toml', 'Cargo.lock', 'crates/reactor/Cargo.toml']
    flags = {key: value for key, value in env.items() if key in {
        'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_TARGET',
        'RUSTC', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTUP_TOOLCHAIN',
        'CC', 'CFLAGS', 'CPPFLAGS', 'AR',
    } or (key.startswith('CARGO_TARGET_') and key.endswith(('_RUSTFLAGS', '_LINKER')))}
    identity = dict(compiler=compiler, platform=sys.platform,
                    manifests={name: sha(root/name) for name in manifests},
                    flags_sha256=hashlib.sha256(json.dumps(flags, sort_keys=True).encode()).hexdigest(),
                    cargo_arguments=['build', '--offline', '--release', '-p', 'swoole-rs-reactor'])
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    target = (cache_root or out.parent/'reactor-rust-asan-dependencies')/key
    if target.is_relative_to(out) or out.is_relative_to(target):
        raise ValueError('Dependency intermediates must be outside unique final artifacts')
    return target, identity


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True, help='Read-only pinned upstream Git source')
    p.add_argument('--target', type=Path, required=True, help='Private output directory')
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--dependency-target-root', type=Path, help='Same-owner persistent PRIVATE Cargo intermediates root; never a cross-owner target. Default is a sibling of --target.')
    profile = p.add_mutually_exclusive_group()
    profile.add_argument('--snapshot-only', action='store_true', help='Only the positive snapshot gate; no historical callback/lifetime profiles')
    profile.add_argument('--flush-only', action='store_true', help='Only positive writable/drain effect facades; no callbacks/fault probes')
    profile.add_argument('--backend-only', action='store_true', help='Only positive kernel event arrays and filtered positive Rust units; no allocation/fault/lifetime probes')
    profile.add_argument('--wait-only', action='store_true', help='Only positive complete wait effects and filtered positive units; no faults/allocation/lifetime probes')
    profile.add_argument('--batch-only', action='store_true', help='Only positive genuine array decode/full wait effects; no faults/allocation/lifetime probes')
    profile.add_argument('--callbacks-only', action='store_true', help='Only positive ordered callback storage/ordinary Native effects; no lifetime/fault probes')
    profile.add_argument('--builtins-only', action='store_true', help='Only normal deferred/begin/idle/exit orchestration with the Rust-owned deferred queue; no fault/lifetime probes')
    profile.add_argument('--output-only', action='store_true', help='Only four ordinary positive Socket output compositions; no faults/EINTR/lifetime probes')
    profile.add_argument('--iov-progress-only', action='store_true', help='Only genuine iovec array positive progress; no I/O/fault/lifetime probes')
    profile.add_argument('--forwarding-only', action='store_true', help='Only file/event forwarding positive source effects; clean Native effects remain unexecuted')
    profile.add_argument('--iov-owned-only', action='store_true', help='Only positive Rust-owned IOVector storage/copy/cursor controls; no allocation failures or lifetime probes')
    args = p.parse_args()
    if not any([args.iov_owned_only,args.snapshot_only,args.flush_only,args.backend_only,args.wait_only,args.batch_only,args.callbacks_only,args.builtins_only,args.output_only,args.iov_progress_only,args.forwarding_only]):
        p.error('Historical unfiltered callback/fault/lifetime profile is stopped; choose a separately named positive profile. No artifacts or checks launched.')
    if args.report.exists(): raise ValueError('Choose a new immutable report path')
    out = args.target.resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Choose an empty private final-artifact directory')
    out.mkdir(parents=True,exist_ok=True)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    source = ROOT/'crates/reactor/src/lib.rs'
    env = dict(os.environ, RUSTC_BOOTSTRAP='1', ASAN_OPTIONS='detect_leaks='+('0' if sys.platform == 'darwin' else '1'))
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),scope=__doc__,
                  rustc=subprocess.check_output(['rustc','-vV'],text=True),commands=[],passed=False,
                  limits='Test-only experimental Rust flags, no production allocator/ABI/config changes. Precompiled Rust standard library is not instrumented. Native facades, not PHP-loaded ASan or concurrent-fork allocator safety.')

    dependencies_target, _ = dependency_target(ROOT, out, report['rustc'], env, args.dependency_target_root.resolve() if args.dependency_target_root else None)
    report['dependency_target'] = str(dependencies_target)

    def run(name, command):
        require_build_space(ROOT)
        require_build_space(out)
        log = out/(name+'.log')
        try:
            proc = run_isolated(list(map(str,command)),cwd=ROOT,env=env,timeout=120)
        except subprocess.TimeoutExpired as error:
            log.write_text(str(error.stdout)+str(error.stderr))
            report['commands'].append(dict(name=name,command=list(map(str,command)),exit=None,log=str(log),error='Timed out; owned process group stopped'))
            raise
        log.write_text(proc.stdout+proc.stderr)
        row=dict(name=name,command=list(map(str,command)),exit=proc.returncode,log=str(log))
        report['commands'].append(row)
        print(name,proc.returncode,flush=True)
        if proc.returncode: raise RuntimeError('Failed '+name+': '+str(log))
        return proc.stdout+proc.stderr

    try:
        require_build_space(ROOT)
        require_build_space(out)
        dependencies_target.mkdir(parents=True,exist_ok=True)
        require_build_space(dependencies_target)
        unit = out/'rust-unit'
        dependencies = run('dependency-build', ['cargo','build','--offline','--release','-p','swoole-rs-reactor','--target-dir',dependencies_target,'--message-format=json'])
        artifacts = [json.loads(line) for line in dependencies.splitlines() if line.startswith('{')]
        libc = [Path(name) for item in artifacts if item.get('reason') == 'compiler-artifact' and item.get('target',{}).get('name') == 'libc' for name in item['filenames'] if name.endswith('.rlib')]
        if len(libc) != 1: raise ValueError('Ambiguous exact Cargo libc artifact')
        base=['rustc','--extern','libc='+str(libc[0]),'-L','dependency='+str(libc[0].parent),'-Ccodegen-units=1','--edition=2024','--crate-name','swoole_rs_reactor','-g','-Copt-level=2','-Zsanitizer=address',source]
        run('unit-compile',base+['--test','-o',unit])
        run('unit', [unit,'--nocapture', *(['iov_owned_positive'] if args.iov_owned_only else ['output_workflow'] if args.forwarding_only else ['iov_progress_positive'] if args.iov_progress_only else ['output_positive'] if args.output_only else ['builtins_positive'] if args.builtins_only else ['callbacks_positive'] if args.callbacks_only else ['batch_positive'] if args.batch_only else ['wait_positive'] if args.wait_only else ['backend_positive'] if args.backend_only else [])])
        archive=out/'libswoole_rs_reactor.a'
        run('archive-compile',base+['--crate-type','staticlib','-Zexternal-clangrt=yes','-o',archive])
        members=run('archive-members',['ar','t',archive]).splitlines()
        members=[name for name in members if '.swoole_rs_reactor.' in name and name.endswith('.rcgu.o')]
        if len(members) != 1: raise ValueError('Ambiguous actual Rust source object: '+str(members))
        obj=out/'reactor-rust.o'
        obj.write_bytes(subprocess.check_output(['ar','p',str(archive),members[0]]))
        report['rust_object']=members[0]
        symbols=run('archive-symbols',['nm','-u',obj])
        imports=[line for line in symbols.splitlines() if '__asan_report_' in line]
        if not imports: raise ValueError('No actual Rust-object ASan report imports')
        report['rust_asan_imports']=imports
        report['asan_options']=env['ASAN_OPTIONS']
        for gate in (['iov_owned'] if args.iov_owned_only else ['output'] if args.output_only or args.iov_progress_only or args.forwarding_only else ['builtins'] if args.builtins_only else ['callbacks'] if args.callbacks_only else ['wait'] if args.batch_only else ['wait'] if args.wait_only else ['backend_storage'] if args.backend_only else ['flush'] if args.flush_only else ['poll_snapshot'] if args.snapshot_only else ['ordered','filters','write','stream']):
            run(gate,['python3',ROOT/('tests/modules/reactor/'+gate+('' if gate in ['poll_snapshot','flush','backend_storage','wait','callbacks','builtins','output','iov_owned'] else '_gate')+'.py'),'--source',args.source.resolve(),'--archive',archive,*(['--forwarding'] if args.forwarding_only else ['--iov-progress'] if args.iov_progress_only else []),'--sanitize','--report',out/(gate+'.json')])
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
    finally:
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
