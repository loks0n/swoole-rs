#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <sys/types.h>
#include <cerrno>
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0,SW_ERR=-1,SW_WAIT=1;
static std::vector<std::string> effects;
#define swoole_error_log(...) assert(false && "unexpected warning in positive write profile")
static void swoole_set_last_error(int) { assert(false && "unexpected error in positive write profile"); }
struct Buffer {
    uint32_t bytes=0;
    Buffer()=default;
    explicit Buffer(uint32_t) { assert(false && "allocation path outside this positive profile"); }
    static bool empty(Buffer *b) { return !b || b->bytes==0; }
    uint32_t length() const { return bytes; }
};
struct Socket {
    Buffer *out_buffer=nullptr;
    uint32_t buffer_size=16,chunk_size=4;
    bool nonblock=true,ssl_send_=false,writable=true;
    static constexpr uint32_t default_buffer_size=16;
    void set_memory_buffer_size(uint32_t) { assert(false); }
    void set_fd_option(int,int) { assert(false); }
    int catch_write_error(int) { assert(false && "no Native fault execution"); return 0; }
    bool isset_writable_event() const { return writable; }
    int get_fd() const { return 7; }
};
#include "write-positive.inc"
template<class Reactor> std::vector<std::string> run(unsigned scenario) {
    effects.clear(); Buffer buffer; Socket socket; Reactor reactor;
    socket.out_buffer=scenario==0?nullptr:&buffer;
    if(scenario==1) buffer.bytes=2;
    socket.ssl_send_=scenario==4;
    socket.writable=scenario!=3;
    ssize_t sent=0;
    std::function<ssize_t()> send=[&]() { effects.emplace_back("send"); sent=scenario==2||scenario==3?1:3; return sent; };
    std::function<void(Buffer*)> append=[&](Buffer *target) {
        assert(target==&buffer); effects.emplace_back("append"); target->bytes+=static_cast<uint32_t>(3-sent);
    };
    assert(Reactor::write_func(&reactor,&socket,3,send,append)==3);
    effects.push_back("bytes="+std::to_string(buffer.bytes));
    effects.push_back("writable="+std::to_string(socket.writable));
    return effects;
}
int main() {
    for(unsigned scenario=0;scenario<5;++scenario) {
        const auto original=run<WriteOriginal>(scenario);
        assert(original==run<WriteSelected>(scenario));
    }
    std::cout<<"{\"positive_write_scenarios\":5,\"allocation_paths_executed\":false,\"native_faults\":false,\"callback_reentry_or_lifetime_probes\":false}\n";
}
