#!/usr/bin/env python3
"""Pure Rust registry tests, including positive ASan, without Native runtime objects."""
import argparse, hashlib, json, os, sys, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    output=a.report.resolve()
    if output.exists():p.error('Choose a unique receipt')
    work=output.parent/('registry-rust-'+uuid.uuid4().hex);work.mkdir(parents=True)
    source=ROOT/'crates/coroutine/src/lib.rs';inputs={str(p):sha(p) for p in source.parent.glob('*.rs')}
    r=dict(passed=False,scope=__doc__,commands=[],work=str(work),rust_asan=a.sanitize,rust_std_instrumented=False,native_runtime_executed=False,measurement_performed=False,activation=False)
    def run(command,env=None):
        require_build_space(work);x=run_isolated(list(map(str,command)),cwd=work,timeout=120,**({'env':env}if env else{}));r['commands'].append(dict(command=list(map(str,command)),cwd=str(work),exit=x.returncode,stdout=x.stdout,stderr=x.stderr));write_report(output,r)
        if x.returncode or x.stderr:raise ValueError('Required command failed or warned')
        return x
    try:
        binary=work/'registry-tests';obj=work/'registry-tests.o'
        command=['rustc','--edition=2024','--test','--crate-name=coroutine_registry','-C','opt-level=2','-D','warnings',source,'--emit=obj='+str(obj)+',link='+str(binary)]
        if a.sanitize:command+=['-Zsanitizer=address']
        run(command,{**os.environ,'RUSTC_BOOTSTRAP':'1'}if a.sanitize else None)
        if a.sanitize:
            observed=run(['nm','-u',obj]);imports=sorted({line.strip() for line in observed.stdout.splitlines()if '__asan_report_'in line});r['owned_test_object_asan_report_imports']=imports
            if not imports:raise ValueError('No positive Rust load/store instrumentation')
        run([binary])
        if not a.sanitize:
            env={**os.environ,'CARGO_TARGET_DIR':str(work/'cargo')}
            run(['cargo','clippy','--quiet','--offline','-p','swoole-rs-coroutine','--all-targets','--','-D','warnings'],env)
            run(['rustfmt','--edition=2024','--check',source])
        if any(sha(Path(p))!=v for p,v in inputs.items()):raise ValueError('Owned source changed')
        r['passed']=True
    except Exception as e:r['error']=str(e)
    write_report(output,r);print(json.dumps({k:r.get(k)for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
