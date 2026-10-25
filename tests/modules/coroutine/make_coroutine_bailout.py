#!/usr/bin/env python3
"""Whole bailout body projection, preserving Native effect text and fallback."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified

CHOSEN='''void Coroutine::bailout(const BailoutCallback &func) {
    swr_v1_coroutine_bailout_cursor cursor = {nullptr, 0};
    uint8_t function_present = 0;
    size_t origin_offset = 0;
    for (;;) {
        const auto step = swr_v1_coroutine_bailout_step(&cursor, &current, function_present, origin_offset);
        switch (step.action) {
        case 0: {
            // marks that it can no longer resume any coroutine
            static BailoutCallback fn = []() {
                // expect that never here
                swoole_error("have been bailout, can not resume any coroutine");
            };
            on_bailout = fn;
            return;
        }
        case 1:
            function_present = !!func;
            break;
        case 2:
            swoole_error("bailout without callback function");
            // fall through: preserve the original sequence if this effect returns.
        case 3: {
            on_bailout = func;
            auto *co = static_cast<Coroutine *>(step.coroutine);
            origin_offset = reinterpret_cast<const unsigned char *>(&co->origin) -
                            reinterpret_cast<const unsigned char *>(co);
            break;
        }
        case 4:
            static_cast<Coroutine *>(step.coroutine)->yield();
            // expect that never here
            exit(SW_CORO_BAILOUT_EXIT_CODE);
        default:
            abort();
        }
    }
}'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args();mp=ROOT/'migration/patches/coroutine/manifest.json';m=json.loads(mp.read_text())
 with tempfile.TemporaryDirectory(prefix='swr-bailout-source-')as temp:
  tree=Path(temp)
  for e in m['patches']:
   for n in e['upstream_paths']:
    f=tree/n
    if not f.exists():f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
   apply_patch_verified(tree,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
  n='src/coroutine/base.cc';f=tree/n;s=f.read_text()
  if '// SWR_BAILOUT_BEGIN'not in s:
   old=block(s,'void Coroutine::bailout(');s=s.replace(old,'#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_BAILOUT_BEGIN\n'+CHOSEN+'\n#else // SWR_BAILOUT_NATIVE\n'+old+'\n#endif // SWR_BAILOUT_END',1);f.write_text(s)
  for e in m['patches']:
   if n not in e['upstream_paths']:continue
   out=''
   for dest in e['upstream_paths']:
    old=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+dest],text=True)
    out+='diff --git a/'+dest+' b/'+dest+'\n'+''.join(difflib.unified_diff(old.splitlines(True),(tree/dest).read_text().splitlines(True),fromfile='a/'+dest,tofile='b/'+dest))
   out=''.join('\n'if line==' \n'else line for line in out.splitlines(True));patch=mp.parent/e['path'];patch.write_text(out);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
  mp.write_text(json.dumps(m,indent=2)+'\n')
if __name__=='__main__':main()
