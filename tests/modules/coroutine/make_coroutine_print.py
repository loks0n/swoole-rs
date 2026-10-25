#!/usr/bin/env python3
"""Whole qualified-owner print loop, Native exact output and map fallback."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
CHOSEN='''void Coroutine::print_list() {
    swr_v1_coroutine_registry_print_cursor cursor = {nullptr, 0};
    const Coroutine *object = nullptr;
    size_t status_offset = 0;
    for (;;) {
        const auto step = coroutines.print_step(&cursor, object, status_offset);
        switch (step.action) {
        case 0: return;
        case 1:
            object = reinterpret_cast<const Coroutine *>(step.token);
            status_offset = reinterpret_cast<const unsigned char *>(&object->status_) -
                            reinterpret_cast<const unsigned char *>(object);
            break;
        case 2:
            object = reinterpret_cast<const Coroutine *>(step.token);
            break;
        case 3:
            sw_printf("Coroutine\\t%ld\\t%s\\n", step.cid, step.label);
            break;
        case 4:
            abort();
            return;
        default:
            abort();
            return;
        }
    }
}'''
PREFIX='#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE && defined(SWOOLE_RS_COROUTINE_REGISTRY_V2) // SWR_PRINT_BEGIN\n'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args();mp=ROOT/'migration/patches/coroutine/manifest.json';m=json.loads(mp.read_text())
 with tempfile.TemporaryDirectory(prefix='swr-print-source-')as temp:
  t=Path(temp)
  for e in m['patches']:
   for n in e['upstream_paths']:
    f=t/n
    if not f.exists():f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
   apply_patch_verified(t,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
  n='src/coroutine/base.cc';f=t/n;s=f.read_text()
  if '// SWR_PRINT_BEGIN'not in s:
   old=block(s,'void Coroutine::print_list()');s=s.replace(old,PREFIX+CHOSEN+'\n#else // SWR_PRINT_NATIVE\n'+old+'\n#endif // SWR_PRINT_END',1);f.write_text(s)
  for e in m['patches']:
   if n not in e['upstream_paths']:continue
   out=''
   for dest in e['upstream_paths']:
    old=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+dest],text=True);out+='diff --git a/'+dest+' b/'+dest+'\n'+''.join(difflib.unified_diff(old.splitlines(True),(t/dest).read_text().splitlines(True),fromfile='a/'+dest,tofile='b/'+dest))
   out=''.join('\n'if line==' \n'else line for line in out.splitlines(True));patch=mp.parent/e['path'];patch.write_text(out);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
  mp.write_text(json.dumps(m,indent=2)+'\n')
if __name__=='__main__':main()
