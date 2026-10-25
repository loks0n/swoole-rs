#!/usr/bin/env python3
"""Project sole typed swap identities and complete lifecycle dispatch callers."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified

GUARD='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
#include <type_traits>
static_assert(sizeof(swr_v1_coroutine_swap_callback) == sizeof(swr_v1_coroutine_swap_function) &&
              alignof(swr_v1_coroutine_swap_callback) == alignof(swr_v1_coroutine_swap_function),
              "Coroutine swap identity requires exact Native function pointer ABI");
#endif
'''
ALIAS_GUARD='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
    static_assert(std::is_same<SwapCallback, swr_v1_coroutine_swap_function>::value,
                  "Coroutine swap C/C++ function pointer linkage requires qualified compiler ABI");
#endif
'''


def wrap(original,chosen):
    return '#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_SWAP_BEGIN\n'+chosen+'\n#else // SWR_SWAP_NATIVE\n'+original+'\n#endif // SWR_SWAP_END'


def dispatch_prefix(name,operation):
    bailout='!!on_bailout' if name=='resume' else '0'
    return '    const auto dispatch = swr_v1_coroutine_dispatch(&status_, SWR_CO_'+operation+', &on_'+name+', &task, '+bailout+');\n    const auto &plan = dispatch.plan;'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    mp=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(mp.read_text())
    with tempfile.TemporaryDirectory(prefix='swr-coroutine-swap-source-') as tmp:
        tree=Path(tmp)
        for e in manifest['patches']:
            for n in e['upstream_paths']:
                path=tree/n
                if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
            apply_patch_verified(tree,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
        hn='include/swoole_coroutine.h';sn='src/coroutine/base.cc';h=(tree/hn).read_text();s=(tree/sn).read_text()
        if 'swr_v1_coroutine_swap_callback on_yield' not in h:
            h=h.replace('namespace swoole {\n',GUARD+'namespace swoole {\n',1)
            alias='    typedef void (*SwapCallback)(void *);';assert h.count(alias)==1;h=h.replace(alias,alias+'\n'+ALIAS_GUARD.rstrip('\n'),1)
            for name in ['yield','resume','close']:
                old='static SW_THREAD_LOCAL SwapCallback on_'+name+';';assert h.count(old)==1
                h=h.replace(old,wrap(old,'static SW_THREAD_LOCAL swr_v1_coroutine_swap_callback on_'+name+';'),1)
                old='SW_THREAD_LOCAL Coroutine::SwapCallback Coroutine::on_'+name+' = nullptr;';assert s.count(old)==1
                s=s.replace(old,wrap(old,'SW_THREAD_LOCAL swr_v1_coroutine_swap_callback Coroutine::on_'+name+' = {nullptr};'),1)
                sig='void Coroutine::set_on_'+name+'(';old=block(s,sig);chosen=old.replace('on_'+name+' = func;','swr_v1_coroutine_swap_publish(&on_'+name+', func);');assert chosen!=old;s=s.replace(old,wrap(old,chosen),1)
                sig='void Coroutine::'+name+'()';old=block(s,sig)
                start=old.index('    const auto plan = ');end=old.index('SWR_CO_STATUS_PUBLISH);',start)+len('SWR_CO_STATUS_PUBLISH);')
                chosen=old[:start]+dispatch_prefix(name,{'yield':'YIELD','resume':'RESUME','close':'CLOSE'}[name])+old[end:]
                chosen=chosen.replace('on_'+name+'(get_task())','dispatch.function(dispatch.task)');assert chosen!=old;s=s.replace(old,chosen,1)
            (tree/hn).write_text(h);(tree/sn).write_text(s)
        for e in manifest['patches']:
            if not any(n in [hn,sn] for n in e['upstream_paths']):continue
            out=''
            for n in e['upstream_paths']:
                before=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True)
                out+='diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(before.splitlines(True),(tree/n).read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))
            out=''.join('\n' if line==' \n' else line for line in out.splitlines(True));patch=mp.parent/e['path'];patch.write_text(out);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
        mp.write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
