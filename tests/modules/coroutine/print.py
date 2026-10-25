#!/usr/bin/env python3
"""Matched complete pinned print bodies on inert foreign records/output accumulation."""
import argparse,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from ordered_gate import ROOT,PIN,block
from channel_state_gate import stage
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['source','archive','report']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();a.report=a.report.resolve()
 if a.report.exists():p.error('Use a unique receipt')
 w=a.report.parent/('coroutine-print-'+uuid.uuid4().hex);w.mkdir(parents=True);mp=ROOT/'migration/patches/coroutine/manifest.json';m=json.loads(mp.read_text());paths=[Path(__file__),Path(__file__).with_suffix('.cc'),a.archive.resolve(),mp,*[mp.parent/e['path']for e in m['patches']],*sorted((ROOT/'native/coroutine').glob('*.h')),*sorted((ROOT/'crates/coroutine/src').glob('*.rs'))];identities={str(v.resolve()):sha(v)for v in paths};r=dict(passed=False,full_gate_passed=False,work=str(w),commands=[],profiles=[],inputs_sha256=identities,runtime_executed=False,actual_function_or_event_executed=False,supplied_archive_source_attested_here=False)
 try:
  current=w/'source';r['patch_proofs']=stage(a.source,current,m,lambda n:(mp.parent/n).read_bytes());native=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':src/coroutine/base.cc'],text=True);selected=(current/'src/coroutine/base.cc').read_text();outputs={}
  for engine,text in [('native',native),('selected',selected)]:
   d=w/engine;d.mkdir();fragments={'print-body.inc':block(text,'void Coroutine::print_list()')}
   for n,v in fragments.items():(d/n).write_text(v+'\n')
   for standard in ['c++14','c++17']:
    for sanitizer in [False,True]:
     binary=d/(standard+'-'+str(sanitizer));command=['c++','-std='+standard,'-O2','-Wall','-Wextra','-Werror','-UNDEBUG',*(['-DSELECTED=1','-DSWOOLE_RS_COROUTINE=1','-DSWOOLE_RS_COROUTINE_REGISTRY_V2']if engine=='selected'else[]),'-I'+str(d),'-I'+str(ROOT/'native/coroutine'),str(Path(__file__).with_suffix('.cc')),*([str(a.archive.resolve())]if engine=='selected'else[]),'-lpthread',*(['-ldl','-lm']if sys.platform=='linux'else[]),*(['-fsanitize=address,undefined','-fno-sanitize-recover=all']if sanitizer else[]),'-o',str(binary)]
     for label,cmd in [('compile',command),('execute',[str(binary)])]:
      require_build_space(w);o=run_isolated(cmd,cwd=d,timeout=120);r['commands'].append(dict(engine=engine,standard=standard,sanitized=sanitizer,stage=label,command=cmd,exit=o.returncode,stdout=o.stdout,stderr=o.stderr));write_report(a.report,r)
      if o.returncode or o.stderr:raise ValueError('Actual inert print source control failed or warned')
     key=standard+'-'+str(sanitizer)
     if engine=='native':outputs[key]=o.stdout
     elif outputs[key]!=o.stdout:raise ValueError('Matched source effects differ')
     r['profiles'].append(dict(engine=engine,standard=standard,sanitized=sanitizer,scenarios=24))
  if any(sha(k)!=v for k,v in identities.items()):raise ValueError('Input changed')
  r['passed']=True
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
