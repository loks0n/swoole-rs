#!/usr/bin/env python3
"""Actual scheduler metadata bodies with inert Context and ordinary Native map.

This is not real Coroutine creation/activation/backend/callback/lifetime evidence.
"""
import argparse,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source','archive','report'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-instrumented',action='store_true');a=p.parse_args();a.report=a.report.resolve()
 if a.rust_instrumented and (sys.platform!='linux' or not a.sanitize):p.error('Mixed instrumentation requires Linux and --sanitize')
 if a.report.exists():p.error('Choose a unique receipt')
 a.report.parent.mkdir(parents=True,exist_ok=True);work=a.report.parent/('scheduler-'+uuid.uuid4().hex);work.mkdir();manifest=ROOT/'migration/patches/coroutine/manifest.json';entries=json.loads(manifest.read_text())['patches'];bound=[Path(__file__),Path(__file__).with_suffix('.cc'),manifest,ROOT/'native/coroutine/swoole_rs_coroutine.h',a.archive.resolve(),*sorted((ROOT/'crates/coroutine/src').glob('*.rs')),*[manifest.parent/e['path']for e in entries]];identities={str(p):sha(p)for p in bound};r=dict(passed=False,full_gate_passed=False,pin=PIN,scope=__doc__,inputs_sha256=identities,native_sanitized=a.sanitize,rust_instrumented=a.rust_instrumented,rust_std_instrumented=False,archive_source_attested_here=False,commands=[],results=[])
 try:
  if a.rust_instrumented:
   imports=subprocess.check_output(['nm','-u',str(a.archive.resolve())],text=True,stderr=subprocess.DEVNULL);r['rust_asan_report_imports']=sorted(set(line.strip()for line in imports.splitlines()if '__asan_report_'in line))
   if not r['rust_asan_report_imports']:raise ValueError('No actual Rust ASan report imports')
  originals={};tree=work/'patched-source'
  for e in entries:
   for n in e['upstream_paths']:
    if n not in originals:
     originals[n]=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True);q=tree/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(originals[n])
  r['patch_proofs']=[apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256'])for e in entries]
  for engine in ('native','selected'):
   folder=work/engine;folder.mkdir();header=originals['include/swoole_coroutine.h']if engine=='native'else(tree/'include/swoole_coroutine.h').read_text();source=originals['src/coroutine/base.cc']if engine=='native'else(tree/'src/coroutine/base.cc').read_text()
   methods=['static size_t get_stack_size()','static void set_stack_size(size_t size)','static void set_socket_bound_cid(long cid)','static long get_last_cid()','static long get_socket_bound_cid()','static uint64_t get_peak_num()','long get_cid() const']
   decl='''class Coroutine {
public:
constexpr static int STACK_ALIGNED_SIZE=4096,MIN_STACK_SIZE=65536,MAX_STACK_SIZE=16777216;
using SwapCallback=void(*)(void*);using BailoutCallback=std::function<void()>;
// Same guards as the identity/swap/creation patches: the selected engine stores Rust-owned slots.
#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
static SW_THREAD_LOCAL swr_v1_coroutine_identity current;
static SW_THREAD_LOCAL swr_v1_coroutine_swap_callback on_yield,on_resume,on_close;
#else
static SW_THREAD_LOCAL Coroutine *current;
static SW_THREAD_LOCAL SwapCallback on_yield,on_resume,on_close;
#endif
static SW_THREAD_LOCAL BailoutCallback on_bailout;
static SW_THREAD_LOCAL std::unordered_map<long,Coroutine*> coroutines;
#ifdef SWOOLE_RS_COROUTINE
static SW_THREAD_LOCAL swr_v1_coroutine_scheduler scheduler_;
static void reset_model(){scheduler_={SW_DEFAULT_C_STACK_SIZE,0,0,0,0};coroutines.clear();on_bailout=nullptr;}
static bool active_model(){return scheduler_.activated;}
#else
static SW_THREAD_LOCAL long last_cid,socket_bound_cid;
static SW_THREAD_LOCAL uint64_t peak_num;
static SW_THREAD_LOCAL size_t stack_size;
static SW_THREAD_LOCAL bool activated;
static void reset_model(){stack_size=SW_DEFAULT_C_STACK_SIZE;last_cid=socket_bound_cid=0;peak_num=0;activated=false;coroutines.clear();on_bailout=nullptr;}
static bool active_model(){return activated;}
#endif
static bool bailout_model(){return bool(on_bailout);}
static size_t count(){observations.push_back(2);return coroutines.size();}
#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
swr_v1_coroutine_cid cid;
#else
long cid;
#endif
Context ctx;
Coroutine(const CoroutineFunc&,void*);
static void activate();static void deactivate();
'''
   decl+='\n'.join(block(header,m)for m in methods)+'\n};\n'
   # Static members start right after the namespace opens; the identity patch guards the first one.
   start=source.index('namespace swoole {\n')+len('namespace swoole {\n');end=source.index('#ifdef SW_USE_THREAD_CONTEXT\nnamespace',start)
   text=decl+source[start:end]+'\n'+block(source,'void Coroutine::activate()')+'\n'+block(source,'void Coroutine::deactivate()')+'\n'+block(source,'Coroutine::Coroutine(')+'\n';inc=folder/'scheduler.inc';inc.write_text(text)
   for threaded in (False,True):
    binary=folder/('metadata-thread'if threaded else'metadata-global');command=['c++','-std=c++14','-O1','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-I'+str(folder),'-I'+str(ROOT/'native/coroutine'),*(['-DSWOOLE_RS_COROUTINE']if engine=='selected'else[]),*(['-DSW_THREAD']if threaded else[]),str(Path(__file__).with_suffix('.cc')),*([str(a.archive.resolve())]if engine=='selected'else[]),'-lpthread',*(['-ldl','-lm']if sys.platform.startswith('linux')else[]),'-o',str(binary)]
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
    for stage,cmd in [('compile',command),('execute',[str(binary)])]:
     require_build_space(work);out=run_isolated(cmd,cwd=folder,timeout=90);r['commands'].append(dict(engine=engine,threaded=threaded,stage=stage,command=cmd,exit=out.returncode,stdout=out.stdout,stderr=out.stderr));write_report(a.report,r)
     if out.returncode or out.stderr:raise ValueError(engine+' '+stage+' failed or warned')
    r['results'].append(dict(engine=engine,threaded=threaded,summary=json.loads(out.stdout)))
  if any(x['summary']!=r['results'][0]['summary']for x in r['results']):raise ValueError('Native/selected metadata observations differ')
  if any(sha(p)!=v for p,v in identities.items()):raise ValueError('Input changed')
  r.update(passed=True,inputs_before_after_equal=True)
 except Exception as e:r['error']=str(e)
 write_report(a.report,r);print(json.dumps({k:r.get(k)for k in ('passed','error','results')}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
