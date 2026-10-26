#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <unordered_map>
#include <vector>
#include <thread>
#include <climits>
#include "swoole_rs_coroutine.h"
#ifdef SW_THREAD
#define SW_THREAD_LOCAL thread_local
#else
#define SW_THREAD_LOCAL
#endif
#define SW_DEFAULT_C_STACK_SIZE (2*1024*1024)
#define SW_MEM_ALIGNED_SIZE_EX(n, alignment) (((n)+(alignment)-1)&~((alignment)-1))
#define SW_MAX(a,b) ((a)>(b)?(a):(b))
#define SW_MIN(a,b) ((a)<(b)?(a):(b))
#define sw_unlikely(x) (x)
using CoroutineFunc=std::function<void(void*)>;
static SW_THREAD_LOCAL std::vector<int> observations;
static SW_THREAD_LOCAL size_t observed_stack;
struct Context {
    Context(size_t size,const CoroutineFunc&,void*) { observed_stack=size;observations.push_back(1); }
};
[[noreturn]] static void swoole_error(const char*) { std::abort(); }
#include "scheduler.inc"
static std::uint64_t exercise() {
    Coroutine::reset_model();observations.clear();
    std::uint64_t checksum=0;
    const size_t requested[]={0,1,65535,65536,65537,16777215,16777216,SIZE_MAX};
    const size_t expected[]={65536,65536,65536,65536,69632,16777216,16777216,16777216};
    for(size_t i=0;i<8;i++) {
        Coroutine::set_stack_size(requested[i]);assert(Coroutine::get_stack_size()==expected[i]);
        Coroutine a({},nullptr);
        assert(observed_stack==expected[i]);assert(a.get_cid()==long(i+1));
        assert(Coroutine::count()==1);assert(Coroutine::get_last_cid()==long(i+1));
        assert(Coroutine::get_peak_num()==1);assert(Coroutine::active_model());
        Coroutine::coroutines.clear();
        Coroutine::set_socket_bound_cid(-long(i)-1);assert(Coroutine::get_socket_bound_cid()==-long(i)-1);
        checksum=checksum*33+observed_stack+a.get_cid();
    }
    Coroutine::deactivate();assert(!Coroutine::active_model());assert(Coroutine::bailout_model());
    Coroutine a({},nullptr),b({},nullptr),c({},nullptr);
    assert(Coroutine::get_peak_num()==3);assert(Coroutine::active_model());assert(!Coroutine::bailout_model());
    Coroutine::coroutines.clear();
    // Every constructor first observes Context, then registration count; peak
    // updates retain the second count. Counts below are fixture observations.
    size_t contexts=0,counts=0;
    for(int n:observations){contexts+=n==1;counts+=n==2;}
    assert(contexts==11);assert(counts==22);
    checksum=checksum*33+contexts*100+counts;
    return checksum;
}
int main(){
    const auto result=exercise();
#ifdef SW_THREAD
    std::uint64_t other=0;std::thread child([&](){other=exercise();});child.join();assert(other==result);
#endif
    std::printf("{\"checksum\":%llu,\"scenarios\":11,\"record_size\":%zu,\"record_align\":%zu}\n",(unsigned long long)result,sizeof(swr_v1_coroutine_scheduler),alignof(swr_v1_coroutine_scheduler));
}
