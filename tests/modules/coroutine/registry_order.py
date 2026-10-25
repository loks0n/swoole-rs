#!/usr/bin/env python3
"""Source-bound live long-key registry order, member/null/update/erase/clear controls.
Only inert metadata: no Coroutine/PHP/list/context/callback/lifecycle execution.
"""
import argparse, hashlib, json, os, subprocess, sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--archive', type=Path, help='Supplied full FFI archive; validate actual ABI1 and coroutine bit, do not compile replacement Rust')
    sanitizer=p.add_mutually_exclusive_group()
    sanitizer.add_argument('--sanitize', action='store_true', help='Instrument actual Rust and C++ metadata accesses with ASan')
    sanitizer.add_argument('--native-sanitize', action='store_true', help='Instrument C++ with ASan/UBSan; ordinary uninstrumented Rust archive')
    a=p.parse_args(); output=a.report.resolve()
    if output.exists(): p.error('Use a unique receipt')
    if a.archive and a.sanitize: p.error('Supplied archive instrumentation is unknown; use separate --native-sanitize or default module-only Rust profile')
    work=output.parent/('registry-order-'+uuid.uuid4().hex); work.mkdir(parents=True)
    paths=[Path(__file__),Path(__file__).with_suffix('.cc'),ROOT/'crates/coroutine/src/lib.rs',ROOT/'native/coroutine/swoole_rs_coroutine_registry.h',ROOT/'native/coroutine/swoole_rs_coroutine.h']
    if a.archive: paths.append(a.archive.resolve())
    identities={str(x):sha(x) for x in [*paths,*sorted((ROOT/'crates/coroutine/src').glob('*.rs')),*sorted((ROOT/'native/coroutine').glob('*.h'))]}
    r=dict(passed=False,scope=__doc__,work=str(work),inputs_sha256=identities,commands=[],results=[],native_runtime_executed=False,archive_kind='supplied-ffi' if a.archive else 'compiled-module',archive_source_attested_here=not bool(a.archive),rust_instrumented=a.sanitize,native_cpp_instrumented=a.sanitize or a.native_sanitize,rust_std_instrumented=False,measurement_performed=False,activation=False)
    def run(command, environment=None):
        require_build_space(work)
        x=run_isolated(list(map(str,command)),cwd=work,timeout=120,**({'env':environment} if environment else {}))
        r['commands'].append(dict(command=list(map(str,command)),cwd=str(work),exit=x.returncode,stdout=x.stdout,stderr=x.stderr));write_report(output,r)
        if x.returncode or x.stderr:
            if 'Coroutine registry ON requires Apple libc++210106 ABI1' in x.stderr:
                r['unsupported_native_order_policy']=True
                raise ValueError('Selected registry order policy unsupported; capability remains OFF')
            raise ValueError('Required command failed or warned')
        return x
    try:
        archive=a.archive.resolve() if a.archive else work/'libregistry.a'
        rust=['rustc','--edition=2024','--crate-type=staticlib','--crate-name=coroutine_registry','-C','opt-level=2','-D','warnings',paths[2],'-o',archive]
        if a.sanitize: rust+=['-Zsanitizer=address']
        if not a.archive: run(rust,{**os.environ,'RUSTC_BOOTSTRAP':'1'} if a.sanitize else None)
        if a.sanitize:
            members=subprocess.check_output(['ar','t',str(archive)],text=True).splitlines()
            own=[name for name in members if '.coroutine_registry.' in name and name.endswith('.rcgu.o')]
            if not own:raise ValueError('Owned registry object absent from archive')
            observed=[]
            for index,member in enumerate(own):
                obj=work/('registry-instrumentation-'+str(index)+'.o')
                obj.write_bytes(subprocess.check_output(['ar','p',str(archive),member]))
                nm=run_isolated(['nm','-u',str(obj)],timeout=120)
                imports=sorted({line.strip() for line in nm.stdout.splitlines() if '__asan_report_' in line})
                observed.append(dict(member=member,exit=nm.returncode,stderr=nm.stderr,asan_report_imports=imports))
                if nm.returncode:raise ValueError('Owned registry instrumentation inspection failed')
            r['rust_instrumentation']=observed
            if not any(row['asan_report_imports'] for row in observed):raise ValueError('Positive Rust ASan instrumentation absent')
        # Bind the actual Native stdlib header bodies, not only a vendor label.
        preprocess=run(['c++','-std=c++14','-M','-x','c++','-include','unordered_map','/dev/null'])
        import shlex
        headers=[Path(x) for x in shlex.split(preprocess.stdout.replace('\\\n',' '))[1:] if Path(x).is_file()]
        r['stdlib_headers_sha256']={str(x):sha(x) for x in headers}
        for standard in ['c++14','c++17']:
            for optimize in ['-O0','-O2']:
                binary=work/(standard+optimize)
                command=['c++','-std='+standard,optimize,'-g','-UNDEBUG','-Wall','-Wextra','-Werror','-DSWOOLE_RS_COROUTINE_REGISTRY_V2=1','-I'+str(ROOT/'native/coroutine'),paths[1],archive,'-lpthread','-lm','-o',binary]
                if a.archive:command+=['-DSWR_REGISTRY_FFI_ARCHIVE=1']
                if a.sanitize:command+=['-fsanitize=address','-fno-sanitize-recover=all']
                elif a.native_sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
                run(command)
                result=run([binary]);r['results'].append(dict(standard=standard,optimization=optimize,summary=json.loads(result.stdout)))
        if any(sha(Path(x))!=v for x,v in identities.items()):raise ValueError('Owned inputs changed')
        if any(sha(x)!=v for x,v in r['stdlib_headers_sha256'].items()):raise ValueError('Native stdlib inputs changed')
        r['passed']=True
    except Exception as e:r['error']=str(e)
    write_report(output,r);print(json.dumps({k:r.get(k) for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
