// Complete configured class geometry only. No Context object or thread is made.
#include "swoole_coroutine_context.h"
#include <cstddef>
#include <cstdio>
#include <type_traits>
struct Layout : swoole::coroutine::Context {
    static void report() {
#ifdef SWOOLE_RS_COROUTINE
        static_assert(std::is_trivially_copyable<swr_v1_context_stack_cell>::value &&
                      std::is_trivially_copyable<swr_v1_context_extent>::value &&
                      std::is_trivially_copyable<swr_v1_context_completion>::value, "passive POD cells");
        const auto end=offsetof(Layout,end_)+offsetof(swr_v1_context_completion,value);
#else
        const auto end=offsetof(Layout,end_);
#endif
#ifdef SW_USE_THREAD_CONTEXT
        std::printf("{\"backend\":\"thread\",\"size\":%zu,\"align\":%zu,\"function\":%zu,\"thread\":%zu,\"lock\":%zu,\"swap_lock\":%zu,\"private_data\":%zu,\"end\":%zu}",sizeof(Layout),alignof(Layout),offsetof(Layout,fn_),offsetof(Layout,thread_),offsetof(Layout,lock_),offsetof(Layout,swap_lock_),offsetof(Layout,private_data_),end);
#else
#ifdef SWOOLE_RS_COROUTINE
        const auto stack=offsetof(Layout,stack_)+offsetof(swr_v1_context_stack_cell,pointer);
        const auto extent=offsetof(Layout,stack_size_)+offsetof(swr_v1_context_extent,size);
#else
        const auto stack=offsetof(Layout,stack_),extent=offsetof(Layout,stack_size_);
#endif
#ifdef USE_UCONTEXT
        const char *backend="ucontext";
#else
        const char *backend="asm";
#endif
        std::printf("{\"backend\":\"%s\",\"size\":%zu,\"align\":%zu,\"function\":%zu,\"context\":%zu,\"swap\":%zu,\"stack\":%zu,\"extent\":%zu,\"private_data\":%zu,\"end\":%zu",backend,sizeof(Layout),alignof(Layout),offsetof(Layout,fn_),offsetof(Layout,ctx_),offsetof(Layout,swap_ctx_),stack,extent,offsetof(Layout,private_data_),end);
#ifdef USE_VALGRIND
        std::printf(",\"valgrind_id\":%zu",offsetof(Layout,valgrind_stack_id));
#endif
        std::printf("}");
#endif
        std::printf("\n");
    }
};
int main(){Layout::report();}
