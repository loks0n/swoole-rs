#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <initializer_list>
#include <string>
#include <chrono>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef __linux__
#include <linux/futex.h>
#include <sys/syscall.h>
#endif
#include "swoole_rs_utilities.h"
using sw_atomic_t = volatile uint32_t;
#define sw_atomic_cmp_set(p,a,b) __sync_bool_compare_and_swap(p,a,b)
#define sw_atomic_sub_fetch(p,n) __sync_sub_and_fetch(p,n)
#define sw_atomic_fetch_add(p,n) __sync_fetch_and_add(p,n)
namespace reference_fallback {
#include "oracle.inc"
}
namespace rust_fallback {
#include "candidate.inc"
}
#ifdef __linux__
#define HAVE_FUTEX 1
namespace reference_kernel {
#include "oracle.inc"
}
namespace rust_kernel {
#include "candidate.inc"
}
#undef HAVE_FUTEX
#endif
using Wait = int (*)(sw_atomic_t *, double);
using Wake = int (*)(sw_atomic_t *, int);
static size_t checks = 0;
static void require(bool ok, const char *what) {
    ++checks;
    if (!ok) { std::fprintf(stderr,"check failed: %s\n",what); std::abort(); }
}
static void differential(Wait reference, Wait rust, Wake wake_reference, Wake wake_rust, bool kernel) {
    for (uint32_t word : {0u,1u,2u,0x7fffffffu,0x80000000u,0xffffffffu}) {
        for (int n : {INT_MIN,-2,-1,0,1,2,INT_MAX}) {
            sw_atomic_t a=word,b=word;
            errno=EDOM; int ra=wake_reference(&a,n),ea=errno;
            errno=EDOM; int rb=wake_rust(&b,n),eb=errno;
            require(ra==rb && ea==eb && a==b,"wake result/errno/word");
        }
        for (double timeout : {0.000001,0.001,0.0015}) {
            sw_atomic_t a=word,b=word;
            errno=EDOM; int ra=reference(&a,timeout),ea=errno;
            errno=EDOM; int rb=rust(&b,timeout),eb=errno;
            require(ra==rb && ea==eb && a==b,"wait result/errno/word");
        }
        // Nonpositive waits on zero are indefinite; exercise only immediate paths.
        if (word==1 || (kernel && word!=0)) {
            for (double timeout : {-123.0,-0.0,0.0}) {
                sw_atomic_t a=word,b=word;
                errno=EDOM; int ra=reference(&a,timeout),ea=errno;
                errno=EDOM; int rb=rust(&b,timeout),eb=errno;
                require(ra==rb && ea==eb && a==b,"nonpositive immediate wait");
            }
        }
    }
}
static void shared_process(Wait wait, Wake wake, bool kernel) {
    auto *word=static_cast<sw_atomic_t *>(mmap(nullptr,sizeof(uint32_t),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANON,-1,0));
    require(word!=MAP_FAILED,"shared mmap"); *word=0;
    int channel[2];require(pipe(channel)==0,"pipe");
    pid_t child=fork();require(child>=0,"fork");
    if (child==0) {
        close(channel[0]);alarm(5);
        int result=wait(word,2.0);
        bool wrote=write(channel[1],&result,sizeof result)==sizeof result;
        _exit(wrote && result==0 ? 0 : 1);
    }
    close(channel[1]); bool blocked=false;
    auto end=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    while (std::chrono::steady_clock::now()<end) {
        if (!kernel) { blocked=__atomic_load_n(word,__ATOMIC_RELAXED)==UINT32_MAX; }
#ifdef __linux__
        else {
            char path[80],state[128]={};std::snprintf(path,sizeof path,"/proc/%d/wchan",child);
            FILE *f=std::fopen(path,"r");
            if (f) { if (std::fgets(state,sizeof state,f)) blocked=std::string(state).find("futex")!=std::string::npos; std::fclose(f); }
        }
#endif
        if (blocked) break;
        usleep(1000);
    }
    if (!blocked) { kill(child,SIGKILL);waitpid(child,nullptr,0); }
    require(blocked,"child actually waiting before wake");
    require(wake(word,1)==(kernel?1:0),"wake actual shared waiter");
    int result=-2,status=0;
    require(read(channel[0],&result,sizeof result)==sizeof result,"read child result");
    require(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0 && result==0,"shared child completed");
    require(*word==0,"shared final word");close(channel[0]);munmap(const_cast<uint32_t *>(word),sizeof(uint32_t));
}
int main() {
    differential(reference_fallback::sw_atomic_futex_wait,rust_fallback::sw_atomic_futex_wait,reference_fallback::sw_atomic_futex_wakeup,rust_fallback::sw_atomic_futex_wakeup,false);
    shared_process(reference_fallback::sw_atomic_futex_wait,reference_fallback::sw_atomic_futex_wakeup,false);
    shared_process(rust_fallback::sw_atomic_futex_wait,rust_fallback::sw_atomic_futex_wakeup,false);
#ifdef __linux__
    differential(reference_kernel::sw_atomic_futex_wait,rust_kernel::sw_atomic_futex_wait,reference_kernel::sw_atomic_futex_wakeup,rust_kernel::sw_atomic_futex_wakeup,true);
    shared_process(reference_kernel::sw_atomic_futex_wait,reference_kernel::sw_atomic_futex_wakeup,true);
    shared_process(rust_kernel::sw_atomic_futex_wait,rust_kernel::sw_atomic_futex_wakeup,true);
#endif
    std::printf("{\"checks\":%zu,\"shared_processes\":%d}\n",checks,
#ifdef __linux__
    4
#else
    2
#endif
    );
}
