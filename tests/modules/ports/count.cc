// Exact pinned/selected accessor bodies; only external native storage is supplied.
#ifdef PORTS_DRIVER
#include "swoole_rs_ports.h"
#endif
#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <type_traits>
#include <vector>

static_assert(sizeof(std::atomic<uint32_t>) == sizeof(uint32_t), "counter size");
static_assert(alignof(std::atomic<uint32_t>) == alignof(uint32_t), "counter alignment");
using sw_atomic_t = volatile uint32_t;
struct SharedCounters { sw_atomic_t connection_num; sw_atomic_t *connection_nums; };
struct Server { uint32_t worker_num; };
// One instance shared by both translation units.
inline Server server;
inline uint64_t server_reads;
inline Server *sw_server() { ++server_reads; return &server; }
namespace original { struct ListenPort { SharedCounters *gs; size_t get_connection_num() const; }; }
namespace selected { struct ListenPort { SharedCounters *gs; size_t get_connection_num() const; }; }
// Each side's body in its own translation unit; the selected one also holds the driver.
namespace PORTS_SIDE {
#include "body.inc"
}
#ifdef PORTS_DRIVER

int main() {
    uint64_t cases=0, state=0x706f727473;
    auto random=[&]() { state^=state<<13;state^=state>>7;state^=state<<17;return uint32_t(state); };
    for(uint32_t fallback : {0u,1u,0x7fffffffu,0x80000000u,0xffffffffu}) {
        SharedCounters gs{fallback,nullptr};
        server.worker_num=0xffffffffu;server_reads=0;
        assert(original::ListenPort{&gs}.get_connection_num()==fallback);
        assert(selected::ListenPort{&gs}.get_connection_num()==fallback);
        assert(server_reads==0); // No server lookup in the fallback branch.
        assert(swr_v1_ports_connection_count(nullptr,0xffffffffu,fallback)==fallback);
        ++cases;
    }
    for(uint32_t size : {0u,1u,2u,3u,7u,16u,127u,257u,4096u}) {
        std::vector<uint32_t> storage(size+2);
        for(unsigned iteration=0;iteration<256;iteration++) {
            uint64_t expected=0;
            for(auto &cell:storage)cell=random();
            for(uint32_t i=0;i<size;i++) {
                uint32_t value=iteration==0?0xffffffffu:iteration==1?0:storage[i+1];
                storage[i+1]=value;expected+=value;
            }
            SharedCounters gs{random(),storage.data()+1};server.worker_num=size;
            server_reads=0;auto before=original::ListenPort{&gs}.get_connection_num();
            assert(server_reads==uint64_t(size)+1);
            server_reads=0;auto after=selected::ListenPort{&gs}.get_connection_num();
            assert(server_reads==1); // Stable native bound projected once, no reentry.
            assert(before==expected&&after==expected);
            assert(swr_v1_ports_connection_count(storage.data()+1,size,random())==expected);
            assert(swr_v1_ports_connection_count(storage.data()+storage.size(),0,random())==0);
            ++cases;
        }
    }
    std::cout<<"connection-count "<<cases<<" exact-body and direct-ABI cases PASS\n";
}
#endif
