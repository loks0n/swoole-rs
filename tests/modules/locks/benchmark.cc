// Same native public caller, one core library per process, no symbol interposition.
#include "swoole_lock.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <dlfcn.h>

using Clock=std::chrono::steady_clock;
static uint64_t loops;
template<class T> static uint64_t locks(int operation) {
    T lock(false);
    for(int i=0;i<1000;i++){if(lock.lock(operation)||lock.unlock())throw std::runtime_error("warmup");}
    auto start=Clock::now();
    for(uint64_t i=0;i<loops;i++)if(lock.lock(operation)||lock.unlock())throw std::runtime_error("lock operation");
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count();
}
int main(int argc,char**argv){
    if(argc!=4)return 2;std::string workload=argv[1];bool rust=std::string(argv[2])=="rust";loops=std::strtoull(argv[3],nullptr,10);if(!loops||loops>100000000)return 3;
    uint64_t ns=0,checksum=loops;
    if(workload=="mutex")ns=locks<swoole::Mutex>(LOCK_EX);
    else if(workload=="rw-read")ns=locks<swoole::RWLock>(LOCK_SH);
#ifdef HAVE_SPINLOCK
    else if(workload=="spin")ns=locks<swoole::SpinLock>(LOCK_EX);
#endif
    else if(workload=="atomic32"){
        uint32_t word=0;
        using Fn=uint32_t(*)(uint32_t*,uint32_t,uint32_t,uint32_t);auto fn=(Fn)dlsym(RTLD_DEFAULT,"swr_v1_locks_atomic32");if(rust&&!fn)return 4;
        auto start=Clock::now();if(rust){for(uint64_t i=0;i<loops;i++)fn(&word,2,1,0);}else{for(uint64_t i=0;i<loops;i++)__sync_add_and_fetch(&word,1);}
        ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count();if(word!=loops)return 5;checksum=word;
    }else return 6;
    std::cout<<"{\"workload\":\""<<workload<<"\",\"nanoseconds\":"<<ns<<",\"checksum\":"<<checksum<<",\"loops\":"<<loops<<"}"<<std::endl;
}
