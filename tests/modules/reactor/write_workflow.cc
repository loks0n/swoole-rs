// Ordinary successful Native effect model. No allocation, error, lifetime,
// callback reentry or kernel execution; every actual method body is extracted.
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <sys/types.h>
#include <cerrno>
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0,SW_ERR=-1,SW_WAIT=1;
static std::vector<std::string> effects;
#define swoole_error_log(...) assert(false && "unexpected warning in positive workflow")
static void swoole_set_last_error(int) { assert(false && "unexpected error in positive workflow"); }
template<class T> struct Observed {
    T value; const char *name;
    operator T() const { effects.emplace_back(name);return value; }
    Observed &operator=(T v) { effects.emplace_back(std::string("publish-")+name);value=v;return *this; }
};
struct Buffer {
    uint32_t bytes=0;
    Buffer()=default;
    explicit Buffer(uint32_t) { assert(false && "Native allocation outside profile"); }
    static bool empty(Buffer *b) { effects.emplace_back("empty");return !b||b->bytes==0; }
    uint32_t length() const { effects.emplace_back("length");return bytes; }
};
struct Socket {
    Observed<Buffer *> out_buffer{nullptr,"output-pointer"};
    Observed<uint32_t> buffer_size{64,"capacity"};
    uint32_t chunk_size=4;
    Observed<bool> nonblock{true,"nonblock"},ssl_send_{false,"tls-send"};
    bool writable=true;
    static constexpr uint32_t default_buffer_size=64;
    void set_memory_buffer_size(uint32_t value) { effects.emplace_back("default-buffer");buffer_size=value; }
    void set_fd_option(int a,int b) { assert(a==1&&b==-1);effects.emplace_back("set-nonblock");nonblock=true; }
    int catch_write_error(int) { assert(false && "Native fault outside profile");return 0; }
    bool isset_writable_event() const { effects.emplace_back("writable");return writable; }
    int get_fd() const { assert(false);return 7; }
};
#include "write-positive.inc"
template<class Reactor> std::vector<std::string> run(unsigned scenario,uint32_t capacity,bool nonblock) {
    effects.clear();Buffer buffer;Socket socket;Reactor reactor;
    socket.out_buffer.value=scenario==0?nullptr:&buffer;
    socket.buffer_size.value=capacity;socket.nonblock.value=nonblock;
    if(scenario==1)buffer.bytes=2;
    socket.ssl_send_.value=scenario==4;socket.writable=scenario!=3;
    ssize_t sent=0;
    std::function<ssize_t()> send=[&]() { effects.emplace_back("send");sent=scenario==2||scenario==3?1:3;return sent; };
    std::function<void(Buffer*)> append=[&](Buffer *target) {assert(target==&buffer);effects.emplace_back("append");target->bytes+=static_cast<uint32_t>(3-sent);};
    assert(Reactor::write_func(&reactor,&socket,3,send,append)==3);
    effects.push_back("bytes="+std::to_string(buffer.bytes));effects.push_back("writable="+std::to_string(socket.writable));
    return effects;
}
int main() {
    const size_t state[]={sizeof(swr_v1_reactor_write_workflow_state),alignof(swr_v1_reactor_write_workflow_state),offsetof(swr_v1_reactor_write_workflow_state,phase),offsetof(swr_v1_reactor_write_workflow_state,policy_phase)};
    const size_t facts[]={sizeof(swr_v1_reactor_write_facts),alignof(swr_v1_reactor_write_facts),offsetof(swr_v1_reactor_write_facts,buffered),offsetof(swr_v1_reactor_write_facts,sent),offsetof(swr_v1_reactor_write_facts,capacity),offsetof(swr_v1_reactor_write_facts,flags),offsetof(swr_v1_reactor_write_facts,nonblock),offsetof(swr_v1_reactor_write_facts,wait),offsetof(swr_v1_reactor_write_facts,interrupted)};
    for(unsigned i=0;i<4;++i)assert(state[i]==swr_v1_reactor_write_workflow_layout(0,i));
    for(unsigned i=0;i<9;++i)assert(facts[i]==swr_v1_reactor_write_workflow_layout(1,i));
    for(auto capacity:{0u,64u})for(auto nonblock:{false,true})for(unsigned scenario=0;scenario<5;++scenario)assert(run<WriteOriginal>(scenario,capacity,nonblock)==run<WriteSelected>(scenario,capacity,nonblock));
    std::cout<<"{\"positive_workflow_scenarios\":20,\"ordered_fact_and_effect_trace_equal\":true,\"additive_abi_facts\":13,\"allocation_paths_executed\":false,\"native_faults\":false,\"callback_reentry_or_lifetime_probes\":false}\n";
}
