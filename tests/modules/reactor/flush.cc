#include <cassert>
#include <cstdint>
#include <deque>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0, SW_ERR=-1, SW_EVENT_WRITE=1<<10;
static std::vector<std::string> effects;
struct BufferChunk { enum Type { TYPE_DATA, TYPE_SENDFILE, TYPE_CLOSE }; Type type; };
struct Buffer {
    std::deque<BufferChunk> chunks;
    static bool empty(Buffer *b) { return !b || b->chunks.empty(); }
    BufferChunk *front() { return &chunks.front(); }
};
struct Socket {
    Buffer *out_buffer;
    int fd=7;
    bool close_wait=false, send_wait=false, removed=false;
    void *send_timer=nullptr;
    static constexpr double default_write_timeout=1;
    int handle_send() { effects.emplace_back("data"); out_buffer->chunks.pop_front(); return SW_OK; }
    int handle_sendfile() { effects.emplace_back("sendfile"); out_buffer->chunks.pop_front(); return SW_OK; }
    int wait_event(int, int event) { assert(event==SW_EVENT_WRITE); effects.emplace_back("wait"); return SW_OK; }
};
struct Event { Socket *socket; int fd; };
static double sec2msec(double seconds) { return seconds*1000; }
static void swoole_timer_del(void *timer) { assert(timer); effects.emplace_back("timer"); }
#include "flush.inc"
template<class Reactor> std::vector<std::string> run(std::initializer_list<BufferChunk::Type> kinds, bool timer, bool drain) {
    effects.clear(); Buffer buffer; for (auto type:kinds) buffer.chunks.push_back({type});
    Socket socket; socket.out_buffer=&buffer; if(timer) socket.send_timer=&socket;
    Reactor reactor; Event event{&socket, socket.fd};
    if(drain) reactor.drain_write_buffer(&socket);
    else assert(Reactor::_writable_callback(&reactor,&event)==SW_OK);
    effects.push_back("remaining="+std::to_string(buffer.chunks.size()));
    effects.push_back("removed="+std::to_string(socket.removed));
    effects.push_back("timer="+std::to_string(socket.send_timer!=nullptr));
    return effects;
}
int main() {
    unsigned count=0;
    for(bool timer:{false,true}) for(bool drain:{false,true}) {
        for(auto types:{std::initializer_list<BufferChunk::Type>{}, {BufferChunk::TYPE_DATA}, {BufferChunk::TYPE_SENDFILE}, {BufferChunk::TYPE_DATA,BufferChunk::TYPE_SENDFILE,BufferChunk::TYPE_DATA}, {BufferChunk::TYPE_CLOSE}, {BufferChunk::TYPE_DATA,BufferChunk::TYPE_CLOSE}}) {
            const auto original=run<ReactorOriginal>(types,timer,drain);
            const auto selected=run<ReactorSelected>(types,timer,drain);
            assert(original==selected); ++count;
        }
    }
    std::cout<<"{\"positive_cases\":"<<count<<",\"native_effect_trace_pairs\":"<<count<<",\"data_destroy_callbacks\":false,\"native_socket_syscalls\":false}\n";
}
