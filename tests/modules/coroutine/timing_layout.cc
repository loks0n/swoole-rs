#include "swoole_coroutine.h"
#include <cstdio>
#include <cstddef>
class Layout : public swoole::Coroutine {
public:
    static void report() {
#ifdef SWOOLE_RS_COROUTINE
        static_assert(sizeof(swr_v1_coroutine_timing)==3*sizeof(long),"timing storage size");
        static_assert(alignof(swr_v1_coroutine_timing)==alignof(long),"timing storage alignment");
        const auto init=offsetof(Layout,timing_)+offsetof(swr_v1_coroutine_timing,init_msec);
        const auto switched=offsetof(Layout,timing_)+offsetof(swr_v1_coroutine_timing,switch_usec);
        const auto execute=offsetof(Layout,timing_)+offsetof(swr_v1_coroutine_timing,execute_usec);
        static_assert(sizeof(swr_v1_coroutine_status)==8 && alignof(swr_v1_coroutine_status)==4,"lifecycle record ABI");
        const auto state=offsetof(Layout,status_)+offsetof(swr_v1_coroutine_status,state);
        const auto resume=offsetof(Layout,status_)+offsetof(swr_v1_coroutine_status,code);
#else
        const auto init=offsetof(Layout,init_msec),switched=offsetof(Layout,switch_usec),execute=offsetof(Layout,execute_usec);
        const auto state=offsetof(Layout,state),resume=offsetof(Layout,resume_code_);
#endif
        std::printf("{\"size\":%zu,\"align\":%zu,\"state\":%zu,\"resume\":%zu,\"cid\":%zu,\"init\":%zu,\"switch\":%zu,\"execute\":%zu,\"task\":%zu,\"context\":%zu,\"origin\":%zu,\"cancel\":%zu}\n",sizeof(Layout),alignof(Layout),state,resume,offsetof(Layout,cid),init,switched,execute,offsetof(Layout,task),offsetof(Layout,ctx),offsetof(Layout,origin),offsetof(Layout,cancel_fn_));
    }
};
int main(){Layout::report();}
