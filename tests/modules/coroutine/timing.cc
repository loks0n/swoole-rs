#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
#include <cstddef>
#include "swoole_rs_coroutine.h"
static long clock_value=0;
static std::vector<int> clock_order;
struct Timer { static long get_absolute_msec() { clock_order.push_back(1); return 123; } };
using seconds_type=int;
template<class T> long time(bool monotonic) { assert(monotonic); clock_order.push_back(2); return clock_value; }
struct Context { Context() { clock_order.push_back(3); } };
#include "timing.inc"
int main() {
    std::uint64_t checksum=0; std::size_t checks=0;
    for(long start=10;start<=500;start+=10) {
        clock_order.clear();clock_value=start;Coroutine a;
        assert((clock_order==std::vector<int>{1,2,3}));++checks;
        clock_order.clear();Coroutine b;assert((clock_order==std::vector<int>{1,2,3}));++checks;
        assert(a.get_init_msec()==123);++checks;
        long expected=0,last=start;
        for(int n=0;n<80;n++) {
            clock_value=start+n*5;
            expected+=clock_value-last;
            Coroutine::calc_execute_usec(&a,&a); last=clock_value;
            clock_order.clear();const Coroutine &read=a;
            assert(read.get_execute_usec()==expected);assert((clock_order==std::vector<int>{2}));checks+=2;
            checksum=checksum*33+read.get_execute_usec();
            clock_value+=3;
            Coroutine::calc_execute_usec(&a,&b);expected+=3;
            assert(a.get_execute_usec()==expected+3);++checks;
            Coroutine::calc_execute_usec(nullptr,&a);last=clock_value;
            assert(a.get_execute_usec()==expected);++checks;
            clock_order.clear();Coroutine::calc_execute_usec(nullptr,nullptr);
            assert((clock_order==std::vector<int>{2}));++checks;
            clock_value-=2; // Defined negative delta: no overflow or clock assumptions.
            Coroutine::calc_execute_usec(&a,nullptr);expected-=2;
            assert(a.get_execute_usec()==expected-2);++checks;
        }
    }
    std::printf("{\"checks\":%zu,\"checksum\":%llu,\"record_size\":%zu,\"record_align\":%zu}\n",checks,(unsigned long long)checksum,sizeof(swr_v1_coroutine_timing),alignof(swr_v1_coroutine_timing));
}
