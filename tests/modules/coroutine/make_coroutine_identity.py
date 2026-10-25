#!/usr/bin/env python3
"""Project the whole coupled identity owner with exact existing Native fallback."""
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified


def selected(text):
    """Select only module guards; preserve every unrelated preprocessor branch."""
    output=[];stack=[]
    for line in text.splitlines(True):
        directive=line.strip()
        if directive.startswith(('#if ', '#ifdef ', '#ifndef ')):
            target=directive in ['#ifdef SWOOLE_RS_COROUTINE','#ifndef SWOOLE_RS_COROUTINE']
            parent=all(item[1] for item in stack)
            keep=directive!='#ifndef SWOOLE_RS_COROUTINE' if target else True
            stack.append([target,keep,parent])
            if not target and parent:output.append(line)
        elif directive.startswith('#else'):
            target,keep,parent=stack[-1]
            if target:stack[-1][1]=not keep
            elif parent:output.append(line)
        elif directive.startswith('#endif'):
            target,keep,parent=stack.pop()
            if not target and parent:output.append(line)
        elif all(item[1] for item in stack):output.append(line)
    assert not stack
    return ''.join(output)


def wrap(original,chosen):
    return '#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE // SWR_IDENTITY_BEGIN\n'+chosen+'\n#else // SWR_IDENTITY_NATIVE\n'+original+'\n#endif // SWR_IDENTITY_END'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    mp=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(mp.read_text())
    with tempfile.TemporaryDirectory(prefix='swr-coroutine-identity-source-') as tmp:
        tree=Path(tmp)
        for e in manifest['patches']:
            for n in e['upstream_paths']:
                path=tree/n
                if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
            apply_patch_verified(tree,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
        hn='include/swoole_coroutine.h';sn='src/coroutine/base.cc';h=(tree/hn).read_text();s=(tree/sn).read_text()
        if 'swr_v1_coroutine_identity current' not in h:
            for old,new in [('static SW_THREAD_LOCAL Coroutine *current;','static SW_THREAD_LOCAL swr_v1_coroutine_identity current;'),('void *task = nullptr;','swr_v1_coroutine_identity task = {nullptr};'),('Coroutine *origin = nullptr;','swr_v1_coroutine_identity origin = {nullptr};'),('CancelFunc *cancel_fn_ = nullptr;','swr_v1_coroutine_identity cancel_fn_ = {nullptr};')]:
                assert h.count(old)==1;h=h.replace(old,wrap(old,new),1)
            old='SW_THREAD_LOCAL Coroutine *Coroutine::current = nullptr;';assert s.count(old)==1;s=s.replace(old,wrap(old,'SW_THREAD_LOCAL swr_v1_coroutine_identity Coroutine::current = {nullptr};'),1)
            marker='namespace swoole {\n';guard='''#if defined(SWOOLE_RS_COROUTINE) && SWOOLE_RS_COROUTINE
static_assert(sizeof(swr_v1_coroutine_identity) == sizeof(void *) && alignof(swr_v1_coroutine_identity) == alignof(void *) &&
              sizeof(Coroutine *) == sizeof(void *), "Coroutine identity requires exact Native pointer ABI");
#endif
'''
            # Coroutine forward declaration is not available here: void* ABI guard
            # plus complete actual layout witnesses bind all typed Native pointers.
            guard=guard.replace(' &&\n              sizeof(Coroutine *) == sizeof(void *)','')
            h=h.replace(marker,guard+marker,1)
            methods={
                'Coroutine *get_origin() const':'return static_cast<Coroutine *>(swr_v1_coroutine_identity_read(&origin));',
                'long get_origin_cid() const':'return sw_likely(get_origin()) ? get_origin()->get_cid() : -1;',
                'void *get_task() const':'return swr_v1_coroutine_identity_read(&task);',
                'void set_task(void *_task)':'swr_v1_coroutine_identity_publish(&task, _task);',
                'void set_cancel_fn(CancelFunc *cancel_fn)':'swr_v1_coroutine_identity_publish(&cancel_fn_, cancel_fn);',
                'static Coroutine *get_current()':'return static_cast<Coroutine *>(swr_v1_coroutine_identity_read(&current));',
                'static Coroutine *get_current_safe()':'if (sw_unlikely(!get_current())) {\n            swoole_fatal_error(SW_ERROR_CO_OUT_OF_COROUTINE, "API must be called in the coroutine");\n        }\n        return get_current();',
                'static void *get_current_task()':'return sw_likely(get_current()) ? get_current()->get_task() : nullptr;',
                'static long get_current_cid()':'return sw_likely(get_current()) ? get_current()->get_cid() : -1;'}
            for sig,body in methods.items():
                old=block(h,sig);new=old[:old.index('{')+1]+'\n        '+body+'\n    }';h=h.replace(old,wrap(old,new),1)
            for sig in ['void Coroutine::check_end()', 'long Coroutine::run()', 'void Coroutine::yield()', 'void Coroutine::resume()', 'bool Coroutine::cancel()', 'void Coroutine::close()', 'void Coroutine::bailout(']:
                old=block(s,sig);new=selected(old)
                new=new.replace('origin = current;\n    current = this;', 'swr_v1_coroutine_identity_route(&current, &origin, this, SWR_CO_IDENTITY_ENTER);')
                new=new.replace('current = origin;', 'swr_v1_coroutine_identity_route(&current, &origin, this, SWR_CO_IDENTITY_LEAVE);')
                new=new.replace('current == nullptr','get_current() == nullptr').replace('current == this','get_current() == this').replace('current != this','get_current() != this')
                new=new.replace('CALC_EXECUTE_USEC(origin,','CALC_EXECUTE_USEC(get_origin(),').replace('CALC_EXECUTE_USEC(this, current)','CALC_EXECUTE_USEC(this, get_current())')
                # Short-circuit admission and actual argument each observe the
                # identity at their original read, never across Native callbacks.
                new=new.replace('(task ? SWR_CO_TASK : 0)','(get_task() ? SWR_CO_TASK : 0)').replace('!!task','!!get_task()')
                for name in ['on_yield','on_resume','on_close']:new=new.replace(name+'(task)',name+'(get_task())')
                new=new.replace('(cancel_fn_ ? SWR_CO_CANCELABLE : 0)','(swr_v1_coroutine_identity_read(&cancel_fn_) ? SWR_CO_CANCELABLE : 0)').replace('!!cancel_fn_', '!!swr_v1_coroutine_identity_read(&cancel_fn_)')
                new=new.replace('auto fn = *cancel_fn_;','auto fn = *static_cast<CancelFunc *>(swr_v1_coroutine_identity_read(&cancel_fn_));')
                new=new.replace('Coroutine *co = current;','Coroutine *co = get_current();').replace('co->origin','co->get_origin()')
                assert new!=old,(sig,new)
                s=s.replace(old,wrap(old,new),1)
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
