#!/usr/bin/env python3
"""Complete core entry wrappers and one typed Native effect driver."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
DRIVER='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_ENTRY_DRIVER_BEGIN
template <typename Function>
static long run_coroutine_entry(uint32_t mode, const Function &fn, void *arg) {
    swr_v1_coroutine_entry_cursor cursor = {mode, 0, 0, 0};
    long observed = 0;
    for (;;) {
        const auto step = swr_v1_coroutine_entry_step(&cursor, observed);
        switch (step.action) {
        case 0: observed = swoole_event_is_available(); break;
        case 1: observed = swoole_event_init(SW_EVENTLOOP_WAIT_EXIT); break;
        case 2: Coroutine::activate(); break;
        case 3: observed = Coroutine::create(fn, arg); break;
        case 4: swoole_event_wait(); break;
        case 5: Coroutine::deactivate(); break;
        case 6: return step.result;
        default: abort();
        }
    }
}
#endif // SWR_ENTRY_DRIVER_END

'''
def wrap(old,new):return '#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_ENTRY_BEGIN\n'+new+'\n#else // SWR_ENTRY_NATIVE\n'+old+'\n#endif // SWR_ENTRY_END'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args();mp=ROOT/'migration/patches/coroutine/manifest.json';m=json.loads(mp.read_text())
 with tempfile.TemporaryDirectory(prefix='swr-entry-source-')as temp:
  t=Path(temp)
  for e in m['patches']:
   for n in e['upstream_paths']:
    f=t/n
    if not f.exists():f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
   apply_patch_verified(t,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
  n='src/coroutine/base.cc';f=t/n;s=f.read_text()
  if '// SWR_ENTRY_DRIVER_BEGIN'not in s:
   marker='namespace coroutine {\nbool run(';assert marker in s;s=s.replace(marker,DRIVER+marker,1)
   for sig,new in [('bool run(const CoroutineFunc &fn, void *arg)', 'bool run(const CoroutineFunc &fn, void *arg) {\n    return run_coroutine_entry(0, fn, arg);\n}'),('long swoole_coroutine_create(', 'long swoole_coroutine_create(void (*routine)(void *), void *arg) {\n    return swoole::run_coroutine_entry(1, routine, arg);\n}')]:
    old=block(s,sig);s=s.replace(old,wrap(old,new),1)
   f.write_text(s)
  for e in m['patches']:
   if n not in e['upstream_paths']:continue
   out=''
   for dest in e['upstream_paths']:
    old=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+dest],text=True);out+='diff --git a/'+dest+' b/'+dest+'\n'+''.join(difflib.unified_diff(old.splitlines(True),(t/dest).read_text().splitlines(True),fromfile='a/'+dest,tofile='b/'+dest))
   out=''.join('\n'if line==' \n'else line for line in out.splitlines(True));patch=mp.parent/e['path'];patch.write_text(out);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
  mp.write_text(json.dumps(m,indent=2)+'\n')
if __name__=='__main__':main()
