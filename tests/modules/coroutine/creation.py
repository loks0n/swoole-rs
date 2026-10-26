#!/usr/bin/env python3
"""Matched exact registration/lookup/removal bodies on ordinary inert metadata.
No real Coroutine/Context construction, callback, activation, thread or runtime.
"""
import argparse,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from ordered_gate import ROOT,PIN,block
from channel_state_gate import stage
from creation_source import REMOVE
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','archive','report']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.report=a.report.resolve()
    if a.report.exists():p.error('Use a unique receipt')
    work=a.report.parent/('coroutine-creation-'+uuid.uuid4().hex);work.mkdir(parents=True)
    mp=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(mp.read_text())
    paths=[Path(__file__),Path(__file__).with_suffix('.cc'),Path(__file__).with_suffix('.c'),Path(__file__).with_name('creation_source.py'),Path(__file__).with_name('make_coroutine_creation.py'),a.archive.resolve(),mp,*[mp.parent/e['path']for e in manifest['patches']],*sorted((ROOT/'native/coroutine').glob('*.h')),*sorted((ROOT/'crates/coroutine/src').glob('*.rs'))]
    identities={str(path.resolve()):sha(path)for path in paths}
    r=dict(passed=False,full_gate_passed=False,scope=__doc__,pin=PIN,work=str(work),commands=[],profiles=[],
           input_sha256=identities,supplied_archive_source_attested_here=False,runtime_executed=False,
           actual_Coroutine_or_Context_constructed=False,callback_invoked=False,measurement_performed=False,
           limits=['Exact PIN registration BODY and actual selected body in supplemental inert metadata facades; Context initialization expressly excluded/unexecuted.',
                   'Native activation body is not executed: facade toggles initialized metadata only.',
                   'Actual Linux/runtime/lifetime/failure/ZTS/externalSDK/performance/default gates remain open.'])
    def run(command):
        require_build_space(work);out=run_isolated(list(map(str,command)),cwd=work,timeout=120)
        r['commands'].append(dict(command=list(map(str,command)),exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
        if out.returncode or out.stderr:raise ValueError('Required inert source-body control failed or warned')
        return out
    try:
        current=work/'current'
        r['patch_proofs']=stage(a.source,current,manifest,lambda n:(mp.parent/n).read_bytes())
        native_source=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':src/coroutine/base.cc'],text=True)
        native_header=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':include/swoole_coroutine.h'],text=True)
        selected_source=(current/'src/coroutine/base.cc').read_text();selected_header=(current/'include/swoole_coroutine.h').read_text()
        fragments={}
        for engine,source,header in [('native',native_source,native_header),('selected',selected_source,selected_header)]:
            ctor=block(source,'Coroutine::Coroutine(');fragments[engine+'-registration.inc']=ctor[ctor.index('{')+1:ctor.rindex('}')]
            fragments[engine+'-cid.inc']=block(header,'long get_cid() const')
            fragments[engine+'-lookup.inc']=block(header,'static Coroutine *get_by_cid(')
            close=block(source,'void Coroutine::close()')
            remove='    coroutines.erase(cid);' if engine=='native'else REMOVE
            if close.count(remove)!=1:raise ValueError('Exact pre-delete removal fragment missing')
            fragments[engine+'-remove.inc']=remove+'\n'
        for name,text in fragments.items():(work/name).write_text(text)
        for backend in ['genuineNativeMap']:
            for standard in ['c++14','c++17']:
                for sanitized in [False,True]:
                    binary=work/(backend+'-'+standard+'-'+str(sanitized));sanitizer=['-fsanitize=address,undefined','-fno-sanitize-recover=all']if sanitized else[]
                    command=['c++','-std='+standard,'-O2','-Wall','-Wextra','-Werror','-UNDEBUG','-I'+str(work),'-I'+str(ROOT/'native/coroutine'),Path(__file__).with_suffix('.cc'),a.archive.resolve(),'-lpthread',*(['-ldl','-lm']if sys.platform=='linux'else[]),*sanitizer,'-o',binary]
                    row=dict(backend=backend,standard=standard,native_sanitized=sanitized,rust_instrumented=False,status='NOT_RUN');r['profiles'].append(row)
                    try:run(command)
                    except ValueError:
                        row['status']='FAILED'
                        raise
                    observed=run([binary]);row.update(status='PASS',summary=json.loads(observed.stdout));write_report(a.report,r)
        if any(sha(path)!=digest for path,digest in identities.items()):raise ValueError('Input changed')
        r['passed']=len(r['profiles'])==4 and all(row['status']=='PASS'for row in r['profiles'])
    except Exception as error:r['error']=str(error)
    write_report(a.report,r);print(json.dumps({key:r.get(key)for key in ['passed','error','work']}));return int(not r['passed'])

if __name__=='__main__':sys.exit(main())
