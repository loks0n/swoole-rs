#!/usr/bin/env python3
"""Project complete CID/creation/registry operation and actual consumer closure."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified

GUARD='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
static_assert(sizeof(swr_v1_coroutine_cid) == sizeof(long) && alignof(swr_v1_coroutine_cid) == alignof(long),
              "Coroutine CID requires exact original long geometry");
#endif
'''


def wrap(original,chosen):
    return '#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_CREATION_BEGIN\n'+chosen+'\n#else // SWR_CREATION_NATIVE\n'+original+'\n#endif // SWR_CREATION_END'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    mp=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(mp.read_text())
    with tempfile.TemporaryDirectory(prefix='swr-coroutine-creation-source-') as tmp:
        tree=Path(tmp)
        for e in manifest['patches']:
            for n in e['upstream_paths']:
                path=tree/n
                if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
            apply_patch_verified(tree,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
        hn='include/swoole_coroutine.h';sn='src/coroutine/base.cc';h=(tree/hn).read_text();s=(tree/sn).read_text()
        if 'swr_v1_coroutine_cid cid;' not in h:
            h=h.replace('namespace swoole {\n',GUARD+'namespace swoole {\n',1)
            s=s.replace('#include \"swoole_rs_coroutine.h\"\n', '#include \"swoole_rs_coroutine.h\"\n#include <new>\n', 1)
            old='    long cid;';assert h.count(old)==1;h=h.replace(old,wrap(old,'    swr_v1_coroutine_cid cid;'),1)
            sig='long get_cid() const';old=block(h,sig);chosen=old.replace('return cid;','return swr_v1_coroutine_cid_read(&cid);');h=h.replace(old,wrap(old,chosen),1)
            sig='static Coroutine *get_by_cid(';old=block(h,sig);chosen=old[:old.index('{')+1]+'''
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
        return coroutines.lookup(cid);
#else
        auto i = coroutines.find(cid);
        return sw_likely(i != coroutines.end()) ? i->second : nullptr;
#endif
    }''';h=h.replace(old,wrap(old,chosen),1)
            sig='Coroutine::Coroutine(';old=block(s,sig);chosen='''Coroutine::Coroutine(const CoroutineFunc &fn, void *private_data) : ctx(get_stack_size(), fn, private_data) {
    swr_v1_coroutine_creation_cursor cursor = {0};
    size_t observed_count = 0;
    for (;;) {
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
        const auto step = coroutines.creation_step(&cursor, &scheduler_, &cid, this, observed_count);
#else
        const auto step = swr_v1_coroutine_create_step(&cursor, &scheduler_, &cid, nullptr,
                                                     reinterpret_cast<uintptr_t>(this), observed_count);
#endif
        switch (step.action) {
        case SWR_CO_CREATE_INSERT:
            coroutines[step.cid] = this;
            break;
        case SWR_CO_CREATE_COUNT:
            observed_count = count();
            break;
        case SWR_CO_CREATE_ACTIVATE:
            activate();
            return;
        case SWR_CO_CREATE_DONE:
            return;
        case SWR_CO_CREATE_ALLOCATION:
            throw std::bad_alloc();
        default:
            abort();
        }
    }
}''';s=s.replace(old,wrap(old,chosen),1)
            sig='long Coroutine::run()';old=block(s,sig);chosen=old.replace('const long _cid = cid;','const long _cid = get_cid();');assert chosen!=old;s=s.replace(old,chosen,1)
            sig='void Coroutine::close()';old=block(s,sig);chosen=old.replace('    coroutines.erase(cid);','''#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
    coroutines.unregister(&cid);
#else
    coroutines.erase(get_cid());
#endif''');assert chosen!=old;s=s.replace(old,chosen,1)
            (tree/hn).write_text(h);(tree/sn).write_text(s)
        if '// SWR_CID_LOOKUP_NATIVE' not in s:
            sig='swoole::Coroutine *swoole_coroutine_get('
            old=block(s,sig);inner=old[old.index('{')+1:-1]
            chosen=old[:old.index('{')+1]+'\n#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE && defined(SWOOLE_RS_COROUTINE_REGISTRY_V2)\n    return swoole::Coroutine::coroutines.lookup(cid);\n#else // SWR_CID_LOOKUP_NATIVE'+inner+'#endif // SWR_CID_LOOKUP_END\n}'
            s=s.replace(old,chosen,1);(tree/sn).write_text(s)
        if '#include <new>\n' not in s:
            s=s.replace('#include \"swoole_rs_coroutine.h\"\n', '#include \"swoole_rs_coroutine.h\"\n#include <new>\n', 1)
            (tree/sn).write_text(s)
        for e in manifest['patches']:
            if not any(n in [hn,sn] for n in e['upstream_paths']):continue
            out=''
            for n in e['upstream_paths']:
                before=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True)
                out+='diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(before.splitlines(True),(tree/n).read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))
            out=''.join('\n' if line==' \n' else line for line in out.splitlines(True));patch=mp.parent/e['path'];patch.write_text(out);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
        mp.write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
