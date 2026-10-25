// Complete actual create_socket body with scripted native ownership/IO boundaries.
#include "swoole_server.h"
#include "swoole_rs_ports.h"
#include <type_traits>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

namespace fixture {
using namespace swoole;
struct ListenPort;
struct Server { bool enable_reuse_port=false; };
static ListenPort *current;
static Server first_server, second_server;
static std::vector<std::string> trace;
static int failure, mutation, last_error;
static void record(const std::string &name) { trace.push_back(name); }
struct Address {
    int assigned_port;
    bool assign(int,const std::string &,int,bool);
    static const char *type_str(int) { return "fixture"; }
};
struct Socket {
    int fd=11,observed_port=1234;
    int set_reuse_port() { errno=41;record("reuse-port");return failure==2?-1:failure==7?1:0; }
    int set_reuse_addr();
    int bind(const Address &address) { errno=43;record("bind:"+std::to_string(address.assigned_port));return failure==5?-1:failure==9?1:0; }
    int get_name() { errno=44;record("name");observed_port=4321;return failure==6?-1:0; }
    int get_port() { return observed_port; }
    int get_fd() { return fd; }
    void free() { record("free");errno=77; }
};
static Socket made;
struct ListenPort {
    struct { void *private_data_2; } protocol;
    Socket *socket=nullptr;
    int type=SW_SOCK_TCP,port=321;
    std::string host="original";
    bool dtls=false;
    bool is_dgram() { return type==SW_SOCK_UDP; }
    bool is_dtls() { return dtls; }
    void close_socket() { record("close");errno=78;socket=nullptr; }
    int create_socket();
};
bool Address::assign(int,const std::string &host,int port,bool resolve) {
    errno=42;record("assign:"+host+":"+std::to_string(port)+":"+std::to_string(resolve));assigned_port=port;
    return failure!=3;
}
int Socket::set_reuse_addr() {
    errno=45;record("reuse-address");
    if(mutation==3){current->host="changed";current->port=999;}
    return failure==4?-1:failure==8?1:0;
}
static Socket *make_socket(int type,int fd_type,int flags) {
    errno=40;record("make:"+std::to_string(type)+":"+std::to_string(fd_type)+":"+std::to_string(flags));
    if(mutation==1)first_server.enable_reuse_port=!first_server.enable_reuse_port;
    if(mutation==2)current->protocol.private_data_2=&second_server;
    return failure==1?nullptr:&made;
}
static void swoole_set_last_error(int error) { last_error=error;record("last-error:"+std::to_string(error)); }
static void warning(const char *format,...) {
    int error=errno;char text[256];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);
    record("warning:"+std::string(text)+":"+std::to_string(error));
    if(mutation==3){first_server.enable_reuse_port=!first_server.enable_reuse_port;errno=66;}
}
#undef swoole_warning
#undef swoole_sys_warning
#define swoole_warning(...) warning(__VA_ARGS__)
#define swoole_sys_warning(...) warning(__VA_ARGS__)
#include "socket.inc"
#undef swoole_warning
#undef swoole_sys_warning
}
int main() {
    static_assert(sizeof(SwrPortsSocketState)==4&&sizeof(SwrPortsSocketInput)==12&&sizeof(SwrPortsSocketAction)==8,"socket workflow ABI");
    for(int mask=0;mask<32;mask++)for(fixture::failure=0;fixture::failure<10;fixture::failure++)for(fixture::mutation=0;fixture::mutation<4;fixture::mutation++) {
        fixture::ListenPort port;fixture::Socket previous;fixture::made=fixture::Socket{};fixture::made.fd=13;
        fixture::current=&port;fixture::trace.clear();fixture::last_error=0;
        fixture::first_server.enable_reuse_port=mask&2;fixture::second_server.enable_reuse_port=!(mask&2);
        port.protocol.private_data_2=&fixture::first_server;port.socket=mask&1?&previous:nullptr;
        port.dtls=mask&4;port.type=mask&8?SW_SOCK_UDP:SW_SOCK_TCP;port.port=mask&16?0:321;
        errno=17;int result=port.create_socket();int error=errno;
        std::cout<<mask<<' '<<fixture::failure<<' '<<fixture::mutation<<' '<<result<<' '<<(port.socket!=nullptr)<<' '<<port.port<<' '<<fixture::last_error<<' '<<error;
        for(const auto &entry:fixture::trace)std::cout<<'|'<<entry;
        std::cout<<'\n';
    }
}
