#!/usr/bin/env python3
"""Generate owned overlays from the pinned Git objects, never edit the reference."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN
SOURCE = ROOT / 'target/upstream/src'


def original(path):
    return subprocess.check_output(['git', '-C', str(SOURCE), 'show', f'{PIN}:{path}'], text=True)


def lock_body(name, kind, condition=''):
    impl = f'{name}Impl' if name != 'SpinLock' else 'pthread_spinlock_t'
    errname = {'Mutex': 'mutex', 'RWLock': 'rwlock', 'SpinLock': 'spin'}[name]
    return f'''#include "swoole_lock.h"
#include "swoole_rs_locks.h"
#include <cstddef>
{condition}
namespace swoole {{
{name}::{name}(bool shared) : Lock({kind}, shared) {{
    const size_t size = swr_v1_locks_size({kind});
    if (!size || swr_v1_locks_align({kind}) > alignof(std::max_align_t)) {{
        throw std::system_error(EINVAL, std::generic_category(), "unsupported Rust lock storage");
    }}
    impl = reinterpret_cast<{impl} *>(shared ? sw_mem_pool()->alloc(size) : ::operator new(size));
    if (!impl) {{ throw std::bad_alloc(); }}
    if (swr_v1_locks_init((void *) impl, {kind}, shared) != 0) {{
        const int error = errno;
        if (shared) {{ sw_mem_pool()->free((void *) impl); }} else {{ ::operator delete((void *) impl); }}
        throw std::system_error(error, std::generic_category(), "pthread_{errname}_init() failed");
    }}
}}
int {name}::lock(int operation, int timeout_msec) {{
    uint32_t capabilities = 0;
#ifdef HAVE_MUTEX_TIMEDLOCK
    capabilities |= 1;
#endif
#ifdef HAVE_RWLOCK_TIMEDRDLOCK
    capabilities |= 2;
#endif
    return swr_v1_locks_lock((void *) impl, {kind}, operation, timeout_msec, capabilities);
}}
int {name}::unlock() {{ return swr_v1_locks_unlock((void *) impl, {kind}); }}
{name}::~{name}() {{
    swr_v1_locks_destroy((void *) impl, {kind});
    if (shared_) {{ sw_mem_pool()->free((void *) impl); }} else {{ ::operator delete((void *) impl); }}
}}
}}  // namespace swoole
{('#endif' if condition else '')}
'''


def generated():
    changes = {}
    for filename, name, kind, condition in [('mutex','Mutex','MUTEX',''),('rw_lock','RWLock','RW_LOCK','#ifdef HAVE_RWLOCK'),('spin_lock','SpinLock','SPIN_LOCK','#ifdef HAVE_SPINLOCK')]:
        path = f'src/lock/{filename}.cc'
        text = original(path)
        changes[path] = text[:text.index('#include')] + lock_body(name,kind,condition)
    path = 'src/lock/barrier.cc'
    text = original(path)
    changes[path] = text[:text.index('#include')] + '''#include "swoole_lock.h"
#include "swoole_rs_locks.h"
namespace swoole {
void Barrier::init(bool shared, int count) {
#ifdef SW_USE_PTHREAD_BARRIER
    shared_ = shared;
    swr_v1_locks_pthread_barrier(&barrier_, sizeof(barrier_), &barrier_attr_, sizeof(barrier_attr_), 0, shared_, count);
#else
    swr_v1_locks_barrier_init((uint32_t *) &count_, (uint32_t *) &barrier_, count);
#endif
}
void Barrier::wait() {
#ifdef SW_USE_PTHREAD_BARRIER
    swr_v1_locks_pthread_barrier(&barrier_, sizeof(barrier_), &barrier_attr_, sizeof(barrier_attr_), 1, shared_, 0);
#else
    swr_v1_locks_barrier_wait((uint32_t *) &count_, (uint32_t *) &barrier_);
#endif
}
void Barrier::destroy() {
#ifdef SW_USE_PTHREAD_BARRIER
    swr_v1_locks_pthread_barrier(&barrier_, sizeof(barrier_), &barrier_attr_, sizeof(barrier_attr_), 2, shared_, 0);
#endif
}
}  // namespace swoole
'''
    for path in ['ext-src/swoole_atomic.cc', 'ext-src/swoole_thread_atomic.cc']:
        text = original(path).replace('#include "swoole_memory.h"', '#include "swoole_memory.h"\n#include "swoole_rs_locks.h"')
        if '#include "swoole_rs_locks.h"' not in text:
            text = text.replace('#include "php_swoole_thread.h"', '#include "php_swoole_thread.h"\n#include "swoole_rs_locks.h"')
        for variable, word, export, cast in [('atomic','uint32_t','swr_v1_locks_atomic32','uint32_t'),('atomic_long','int64_t','swr_v1_locks_atomic64','sw_atomic_long_t')]:
            ptr = f'({word} *) {variable}'
            text = text.replace(f'sw_atomic_add_fetch({variable}, ({cast}) add_value)', f'{export}({ptr}, 2, ({word}) add_value, 0)')
            text = text.replace(f'sw_atomic_sub_fetch({variable}, ({cast}) sub_value)', f'{export}({ptr}, 3, ({word}) sub_value, 0)')
            text = text.replace(f'RETURN_LONG(*{variable});', f'RETURN_LONG({export}({ptr}, 0, 0, 0));')
            text = text.replace(f'sw_atomic_cmp_set({variable}, (sw_atomic_t) cmp_value, (sw_atomic_t) set_value)', f'{export}({ptr}, 4, ({word}) set_value, ({word}) cmp_value)')
            text = text.replace(f'sw_atomic_cmp_set({variable}, (sw_atomic_long_t) cmp_value, (sw_atomic_long_t) set_value)', f'{export}({ptr}, 4, ({word}) set_value, ({word}) cmp_value)')
            for oldcast in ['sw_atomic_t','sw_atomic_long_t','uint32_t']:
                text = text.replace(f'*{variable} = ({oldcast}) value;', f'{export}({ptr}, 1, ({word}) value, 0);')
                text = text.replace(f'*{variable} = ({oldcast}) set_value;', f'{export}({ptr}, 1, ({word}) set_value, 0);')
        text = text.replace('sw_atomic_futex_wait(atomic, timeout)', 'swr_v1_locks_wait((uint32_t *) atomic, timeout, SWR_LOCKS_HAVE_FUTEX)')
        text = text.replace('sw_atomic_futex_wakeup(atomic, (int) n)', 'swr_v1_locks_wakeup((uint32_t *) atomic, (int) n, SWR_LOCKS_HAVE_FUTEX)')
        changes[path] = text
    path = 'src/lock/coroutine_lock.cc'
    text = original(path).replace('#include "swoole_lock.h"', '#include "swoole_lock.h"\n#include "swoole_rs_locks.h"')
    text = text.replace('if (*value == 0) {', 'if (swr_v1_locks_coroutine_release((uint32_t *) value) == 0) {').replace('    *value = 0;\n    cid = 0;', '    cid = 0;')
    before = """    if (current_coroutine == static_cast<Coroutine *>(coroutine) && current_coroutine->get_cid() == cid) {
        return 0;
    }
"""
    text = text.replace(before, """    // Snapshot the original one-time reentrancy check across native suspension.
    const uintptr_t held_cookie = reinterpret_cast<uintptr_t>(coroutine);
    const int64_t held_cid = cid;
    const uintptr_t current_cookie = reinterpret_cast<uintptr_t>(current_coroutine);
    const int64_t current_cid = current_coroutine->get_cid();
""")
    before = """        if (sw_atomic_cmp_set(value, 0, 1)) {
            break;
        }

        if (!blocking) {
            return EBUSY;
        }
"""
    text = text.replace(before, """        const int action = swr_v1_locks_coroutine_try((uint32_t *) value, held_cookie, held_cid,
                                                     current_cookie, current_cid, blocking);
        if (action == 0) { return 0; }
        if (action == 1) { break; }
        if (action == 2) { return EBUSY; }
""")
    text = text.replace('second = (second >= SW_FILE_LOCK_MAX_SECOND) ? SW_FILE_LOCK_DEFAULT_SECOND\n                                                     : SW_MIN(second * 2, SW_FILE_LOCK_MAX_SECOND);', 'second = swr_v1_locks_coroutine_backoff(second, SW_FILE_LOCK_DEFAULT_SECOND, SW_FILE_LOCK_MAX_SECOND);')
    changes[path] = text
    return changes


def main():
    directory = ROOT / 'migration/patches/locks'
    directory.mkdir(parents=True, exist_ok=True)
    patches = []
    for i, (path, text) in enumerate(generated().items(), 1):
        name = f'{i:04}-{Path(path).stem}.patch'
        data = 'diff --git a/'+path+' b/'+path+'\n'+''.join(difflib.unified_diff(original(path).splitlines(True),text.splitlines(True),fromfile='a/'+path,tofile='b/'+path,n=1))
        data = data.replace('\n \n', '\n\n')
        (directory/name).write_text(data)
        patches.append({'path':name,'sha256':hashlib.sha256(data.encode()).hexdigest(),'upstream_paths':[path]})
    (directory/'manifest.json').write_text(json.dumps({'upstream_commit':PIN,'patches':patches},indent=2)+'\n')


if __name__=='__main__':
    main()
