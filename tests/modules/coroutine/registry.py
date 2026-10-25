#!/usr/bin/env python3
"""Actual complete get/count/GDB and typed view on ordinary inert metadata objects.
No real Coroutine construction, PHP list, context, callback/lifecycle or performance.
"""
import argparse,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from ordered_gate import ROOT,PIN
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['source','archive','report']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-instrumented',action='store_true');a=p.parse_args();a.report=a.report.resolve()
 if a.report.exists():p.error('Choose a unique receipt')
 if a.rust_instrumented and (sys.platform!='linux' or not a.sanitize):p.error('Mixed profile requires Linux and --sanitize')
 a.report.parent.mkdir(parents=True,exist_ok=True);work=a.report.parent/('registry-'+uuid.uuid4().hex);work.mkdir();manifest=ROOT/'migration/patches/coroutine/manifest.json';entries=json.loads(manifest.read_text())['patches'];bound=[Path(__file__),Path(__file__).with_suffix('.cc'),Path(__file__).with_suffix('.c'),manifest,a.archive.resolve(),*sorted((ROOT/'native/coroutine').glob('*.h')),*sorted((ROOT/'crates/coroutine/src').glob('*.rs')),*[manifest.parent/e['path']for e in entries]];identities={str(v):digest(v)for v in bound};r=dict(passed=False,full_gate_passed=False,pin=PIN,scope=__doc__,inputs_sha256=identities,commands=[],results=[],native_sanitized=a.sanitize,rust_instrumented=a.rust_instrumented,rust_std_instrumented=False,archive_source_attested_here=False,php_list_order_qualified=False)
 try:
  if a.rust_instrumented:
   imports=subprocess.check_output(['nm','-u',str(a.archive.resolve())],text=True,stderr=subprocess.DEVNULL);r['rust_asan_report_imports']=sorted(set(line.strip()for line in imports.splitlines()if '__asan_report_'in line))
   if not r['rust_asan_report_imports']:raise ValueError('No actual Rust ASan report imports')
  tree=work/'source';originals={}
  for e in entries:
   for n in e['upstream_paths']:
    if n not in originals:
     originals[n]=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True);f=tree/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(originals[n])
  r['patch_proofs']=[apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256'])for e in entries]
  for engine in ['native','selected']:
   folder=work/engine;folder.mkdir();text=originals['src/coroutine/base.cc']if engine=='native'else(tree/'src/coroutine/base.cc').read_text();start=text.index('swoole::Coroutine *swoole_coroutine_get(');inc=folder/'registry-callers.inc';inc.write_text(text[start:]);binary=folder/'registry'
   cmd=['c++','-std=c++14','-O1','-g','-Wall','-Wextra','-Werror','-UNDEBUG','-I'+str(folder),'-I'+str(ROOT/'native/coroutine'),*(['-DSWOOLE_RS_COROUTINE=1','-DSWOOLE_RS_COROUTINE_REGISTRY_V2']if engine=='selected'else[]),str(Path(__file__).with_suffix('.cc')),*([str(a.archive.resolve())]if engine=='selected'else[]),'-lpthread',*(['-ldl','-lm']if sys.platform=='linux'else[]),'-o',str(binary),*(['-fsanitize=address,undefined','-fno-sanitize-recover=all']if a.sanitize else[])]
   for stage,command in [('compile',cmd),('execute',[str(binary)])]:
    require_build_space(work);out=run_isolated(command,cwd=folder,timeout=120);r['commands'].append(dict(engine=engine,stage=stage,command=command,exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
    if out.returncode or out.stderr:raise ValueError(engine+' '+stage+' failed or warned')
   r['results'].append(dict(engine=engine,summary=json.loads(out.stdout)))
  r['c_abi_results']=[]
  for standard in ['c11','c++14','c++17']:
   binary=work/('abi-'+standard);command=['cc'if standard=='c11'else'c++','-x','c'if standard=='c11'else'c++','-std='+standard,'-Wall','-Wextra','-Werror','-UNDEBUG','-I'+str(ROOT/'native/coroutine'),str(Path(__file__).with_suffix('.c')),'-x','none',str(a.archive.resolve()),'-lpthread','-lm',*(['-ldl']if sys.platform=='linux'else[]),'-o',str(binary),*(['-fsanitize=address,undefined','-fno-sanitize-recover=all']if a.sanitize else[])]
   for stage,cmd in [('compile',command),('execute',[str(binary)])]:
    require_build_space(work);out=run_isolated(cmd,cwd=work,timeout=120);r['commands'].append(dict(standard=standard,stage=stage,command=cmd,exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
    if out.returncode or out.stderr:raise ValueError(standard+' '+stage+' failed or warned')
   r['c_abi_results'].append(dict(standard=standard,passed=True))
  r['iteration_order_equal']=r['results'][0]['summary']['iteration_checksum']==r['results'][1]['summary']['iteration_checksum']
  if not r['iteration_order_equal']:raise ValueError('Native/selected ordinary live traversal differs; REGISTRY_V2 remains OFF')
  for key in ['observations','checksum']:
   if r['results'][0]['summary'][key]!=r['results'][1]['summary'][key]:raise ValueError('Native/selected metadata differ: '+key)
  if any(digest(k)!=v for k,v in identities.items()):raise ValueError('Input changed')
  r.update(passed=True,inputs_before_after_equal=True)
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ['passed','error','results','iteration_order_equal','php_list_order_qualified']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
