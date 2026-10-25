// Exact pinned/generated listen body; scripted native socket/log boundaries only.
#include "swoole_rs_ports.h"
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#define SW_OK 0
#define SW_ERR -1

namespace fixture {
struct ListenPort;
static ListenPort *current;
static std::vector<std::string> trace;
struct Socket {
    ListenPort *owner;
    int calls=0,profile=0;
    bool mutate=false;
    int effect(const std::string &,int);
    int listen(int value) { return effect("listen",value); }
    int set_option(int level,int option,int value) { return effect("option:"+std::to_string(level)+":"+std::to_string(option),value); }
    int set_option(int level,int option,const void *data,size_t size) {
        uint32_t h=0;for(size_t n=0;n<size;n++)h=h*31+static_cast<const uint8_t *>(data)[n];
        return effect("bytes:"+std::to_string(level)+":"+std::to_string(option)+":"+std::to_string(size),int(h));
    }
};
struct ListenPort {
    bool listening=false,open_tcp_keepalive=false;
    int backlog=17,port=23,tcp_defer_accept=0,tcp_fastopen=0,tcp_keepidle=19,tcp_keepinterval=29,tcp_keepcount=31,tcp_user_timeout=0,socket_buffer_size=1024;
    uint32_t buffer_high_watermark=0;
    std::string host="fixture";
    Socket *socket;
    int listen();
};
int Socket::effect(const std::string &name,int value) {
    calls++;int result=(calls+profile)%3-1;errno=EIO+calls;
    trace.push_back(name+":"+std::to_string(value)+":"+std::to_string(result)+":"+std::to_string(owner->listening)+":"+std::to_string(owner->buffer_high_watermark));
    if(mutate) {
        if(calls==1)owner->tcp_defer_accept=0;
        if(calls==2){owner->tcp_fastopen=7;owner->open_tcp_keepalive=true;}
        if(calls==3){owner->open_tcp_keepalive=false;owner->tcp_keepinterval=-17;owner->tcp_keepcount=0;owner->tcp_user_timeout=12;}
        if(calls==4)owner->buffer_high_watermark=0;
    }
    return result;
}
static void warning(const char *format,...) {
    int error=errno;char buffer[256];va_list args;va_start(args,format);vsnprintf(buffer,sizeof(buffer),format,args);va_end(args);
    trace.push_back("warning:"+std::string(buffer)+":"+std::to_string(error));
    if(current->socket->mutate) { current->tcp_user_timeout=0;current->tcp_defer_accept=4; }
}
#define swoole_sys_warning(...) warning(__VA_ARGS__)
#include "listen.inc"
#undef swoole_sys_warning
}
int main() {
    static_assert(sizeof(SwrPortsListenState)==4&&sizeof(SwrPortsListenInput)==44&&sizeof(SwrPortsListenAction)==12,"listen ABI");
    for(unsigned mask=0;mask<256;mask++)for(int profile=0;profile<3;profile++)for(bool mutate:{false,true}) {
        fixture::ListenPort port;fixture::Socket socket;port.socket=&socket;socket.owner=&port;socket.profile=profile;socket.mutate=mutate;fixture::current=&port;fixture::trace.clear();
        port.listening=mask&1;port.tcp_defer_accept=mask&2?-1:0;port.tcp_fastopen=mask&4?3:0;
        port.open_tcp_keepalive=mask&8;port.tcp_user_timeout=mask&16?13:-1;port.buffer_high_watermark=mask&32?47:0;
        port.socket_buffer_size=mask&64?INT32_MAX:1;port.tcp_keepcount=mask&128?-3:0;
        errno=17;int result=port.listen();int error=errno;
        std::cout<<mask<<' '<<profile<<' '<<mutate<<' '<<result<<' '<<port.listening<<' '<<port.buffer_high_watermark<<' '<<error;
        for(const auto &entry:fixture::trace)std::cout<<'|'<<entry;
        std::cout<<'\n';
    }
}
