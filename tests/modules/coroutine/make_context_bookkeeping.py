#!/usr/bin/env python3
"""Project the complete Context bookkeeping owner, preserving Native effect bodies."""
from pathlib import Path
import argparse,difflib,hashlib,json,subprocess,sys,tempfile
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);a=p.parse_args();mp=ROOT/'migration/patches/coroutine/manifest.json';manifest=json.loads(mp.read_text())
with tempfile.TemporaryDirectory(prefix='swr-context-bookkeeping-source-') as tmp:
 tree=Path(tmp)
 for e in manifest['patches']:
  for n in e['upstream_paths']:
   out=tree/n
   if not out.exists():out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
  apply_patch_verified(tree,mp.parent/e['path'],e['upstream_paths'],e['sha256'])
 hn='include/swoole_coroutine_context.h';tn='src/coroutine/thread_context.cc';sn='src/coroutine/context.cc'
 for n in [hn,tn]:
  if not(tree/n).exists():(tree/n).parent.mkdir(parents=True,exist_ok=True);(tree/n).write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n]))
 h=(tree/hn).read_text();s=(tree/sn).read_text();t=(tree/tn).read_text()
 if 'swr_v1_context_stack_cell stack_' not in h:
  include='''#ifdef SWOOLE_RS_COROUTINE
#include "swoole_rs_coroutine.h"
static_assert(sizeof(swr_v1_context_stack_cell) == sizeof(char *) && alignof(swr_v1_context_stack_cell) == alignof(char *) &&
              sizeof(swr_v1_context_extent) == sizeof(uint32_t) && alignof(swr_v1_context_extent) == alignof(uint32_t) &&
              sizeof(bool) == 1 && alignof(bool) == 1 && sizeof(swr_v1_context_completion) == 1 && alignof(swr_v1_context_completion) == 1,
              "Context bookkeeping requires exact Native cell ABI");
#endif
'''
  h=h.replace('#include "swoole.h"\n','#include "swoole.h"\n'+include,1)
  old='    char *stack_;\n    uint32_t stack_size_;';assert h.count(old)==1;h=h.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n    swr_v1_context_stack_cell stack_;\n    swr_v1_context_extent stack_size_;\n#else\n'+old+'\n#endif',1)
  old='    bool end_;';assert h.count(old)==1;h=h.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n    swr_v1_context_completion end_;\n#else\n'+old+'\n#endif',1)
  for signature,selected in {'char *get_stack() const':'return static_cast<char *>(swr_v1_context_stack_read(&stack_, &stack_size_).pointer);','size_t get_stack_size() const':'return swr_v1_context_stack_read(&stack_, &stack_size_).size;','bool is_end() const':'return swr_v1_context_completed(&end_);'}.items():
   old=block(h,signature);inner=old[old.index('{')+1:-1];h=h.replace(old,old[:old.index('{')+1]+'\n#ifdef SWOOLE_RS_COROUTINE\n        '+selected+'\n#else'+inner+'#endif\n    }',1)
  def wrap(signature,selected):
   global s
   old=block(s,signature);s=s.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n'+selected+'\n#else\n'+old+'\n#endif',1)
  wrap('Context::Context(','''Context::Context(size_t stack_size, CoroutineFunc fn, void *private_data)
    : fn_(std::move(fn)), stack_size_(swr_v1_context_extent_new(stack_size)), private_data_(private_data) {
    const size_t allocation_size = swr_v1_context_prepare(&end_, &stack_size_);
#ifdef SW_CONTEXT_PROTECT_STACK_PAGE
    int mapflags = MAP_PRIVATE | MAP_ANONYMOUS;
#ifdef __OpenBSD__
    // no-op for Linux and NetBSD, not to enable on FreeBSD as the semantic differs.
    // However, necessary on OpenBSD.
    mapflags |= MAP_STACK;
#endif
    void *allocation = ::mmap(0, allocation_size, PROT_READ | PROT_WRITE, mapflags, -1, 0);
#else
    void *allocation = sw_malloc(allocation_size);
#endif
    const auto admitted = swr_v1_context_stack_step(&stack_, &stack_size_, SWR_CTX_STACK_ADMIT, allocation, 0);
    if (!admitted.present) {
        swoole_fatal_error(SW_ERROR_MALLOC_FAIL, "failed to malloc stack memory.");
        exit(254);
    }
    swoole_trace_log(SW_TRACE_COROUTINE, "alloc stack: size=%u, ptr=%p", static_cast<uint32_t>(admitted.size), admitted.pointer);
    const auto top = swr_v1_context_stack_step(&stack_, &stack_size_, SWR_CTX_STACK_TOP, nullptr, 0);
    void *sp = top.top;
#ifdef USE_VALGRIND
    valgrind_stack_id = VALGRIND_STACK_REGISTER(sp, top.pointer);
#endif
#ifdef USE_UCONTEXT
    if (-1 == getcontext(&ctx_)) {
        swoole_throw_error(SW_ERROR_CO_GETCONTEXT_FAILED);
        const auto failed = swr_v1_context_stack_read(&stack_, &stack_size_);
        sw_free(failed.pointer);
        return;
    }
    ctx_.uc_stack.ss_sp = swr_v1_context_stack_read(&stack_, &stack_size_).pointer;
    ctx_.uc_stack.ss_size = stack_size;
    ctx_.uc_link = nullptr;
    makecontext(&ctx_, (void (*)(void)) & context_func, 1, this);
#else
    const auto setup = swr_v1_context_stack_read(&stack_, &stack_size_);
    ctx_ = swoole_make_fcontext(sp, setup.size, (void (*)(transfer_t)) & context_func);
    swap_ctx_ = nullptr;
#endif
#ifdef SW_CONTEXT_DETECT_STACK_USAGE
    swr_v1_context_stack_step(&stack_, &stack_size_, SWR_CTX_STACK_MARK, nullptr, stack_size);
#endif
#ifdef SW_CONTEXT_PROTECT_STACK_PAGE
    const auto protection = swr_v1_context_stack_read(&stack_, &stack_size_);
    mprotect(protection.pointer, SwooleG.pagesize, PROT_NONE);
#endif
}''')
  wrap('Context::~Context()', '''Context::~Context() {
    const auto observed = swr_v1_context_stack_read(&stack_, &stack_size_);
    if (observed.present) {
        swoole_trace_log(SW_TRACE_COROUTINE, "free stack: ptr=%p", observed.pointer);
#ifdef USE_VALGRIND
        VALGRIND_STACK_DEREGISTER(valgrind_stack_id);
#endif
        const auto releasing = swr_v1_context_stack_read(&stack_, &stack_size_);
#ifdef SW_CONTEXT_PROTECT_STACK_PAGE
        ::munmap(releasing.pointer, releasing.size);
#else
        sw_free(releasing.pointer);
#endif
        swr_v1_context_stack_step(&stack_, &stack_size_, SWR_CTX_STACK_CLEAR, nullptr, 0);
    }
}''')
  wrap('ssize_t Context::get_stack_usage()', '''ssize_t Context::get_stack_usage() {
    return swr_v1_context_stack_step(&stack_, &stack_size_, SWR_CTX_STACK_USAGE, nullptr, 0).size;
}''')
  old='    _this->end_ = true;';assert s.count(old)==1;s=s.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n    swr_v1_context_finish(&_this->end_);\n#else\n'+old+'\n#endif',1)
  old='    end_ = false;';assert t.count(old)==1;t=t.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n    swr_v1_context_prepare(&end_, nullptr);\n#else\n'+old+'\n#endif',1)
  old='    _this->end_ = true;';assert t.count(old)==1;t=t.replace(old,'#ifdef SWOOLE_RS_COROUTINE\n    swr_v1_context_finish(&_this->end_);\n#else\n'+old+'\n#endif',1)
 (tree/hn).write_text(h);(tree/tn).write_text(t);(tree/sn).write_text(s)
 if not any(hn in e['upstream_paths'] for e in manifest['patches']):manifest['patches'].append({'path':'0005-context-bookkeeping.patch','sha256':'','upstream_paths':[hn,tn]})
 for e in manifest['patches']:
  if not any(n in [hn,tn,sn] for n in e['upstream_paths']):continue
  output=''
  for n in e['upstream_paths']:
   original=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+n],text=True);output+='diff --git a/'+n+' b/'+n+'\n'+''.join(difflib.unified_diff(original.splitlines(True),(tree/n).read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))
  output=''.join('\n' if line==' \n' else line for line in output.splitlines(True));patch=mp.parent/e['path'];patch.write_text(output);e['sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
 mp.write_text(json.dumps(manifest,indent=2)+'\n')
