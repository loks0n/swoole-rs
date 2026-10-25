#include <cstdint>
#include <cstdio>
#include <cerrno>
#include <climits>
#include <sys/socket.h>
#include <sys/un.h>
#include <string>
#include <vector>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include "swoole_rs_clients.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_EVENT_READ 1
#define SW_SOCK_UNIX_DGRAM 5
#define SW_ERROR_OUTPUT_BUFFER_OVERFLOW 900
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void(const std::string&)> effect_hook;
static int address_result,connect_result,bind_result,event_result,ssl_result,dns_result,write_result,last_error;
static ssize_t datagram_result;
static void observe(const std::string&what){effects.push_back(what+":"+(probe?probe():""));}
static void hook(const std::string&name){if(effect_hook)effect_hook(name);}
static void record_warning(const char*message){observe("warning:"+std::string(message));}
static void record_sys_warning(const char*message,const char*path){observe("bind-warning:"+std::string(message)+":"+path);}
static int swoole_get_last_error(){observe("get-error");return last_error;}
#define swoole_warning(...) record_warning(__VA_ARGS__)
#define swoole_sys_warning(...) record_sys_warning(__VA_ARGS__)
#define unlink witness_unlink
#define bind witness_bind
#define getpid witness_getpid
static int witness_getpid(){return 31337;}
static int witness_unlink(const char*path){observe("unlink:"+std::string(path));hook("unlink");return -1;}
static int witness_bind(int fd,const sockaddr*address,size_t size){observe("bind:"+std::to_string(fd)+":"+std::to_string(size)+":"+reinterpret_cast<const sockaddr_un*>(address)->sun_path);hook("bind");return bind_result;}
struct Address {};
struct Socket {
    static constexpr uint32_t default_buffer_size=1024;
    int fd=42,socket_type=1;bool removed=false;size_t output_length=0;
    struct {struct {sockaddr_un un{};}addr;}info;
    void set_kernel_timeout(double n){observe("kernel-timeout:"+std::to_string(n));hook("kernel-timeout");}
    void set_timeout(double n){observe("socket-timeout:"+std::to_string(n));hook("socket-timeout");}
    void set_buffer_size(uint32_t n){observe("buffer-size:"+std::to_string(n));hook("buffer-size");}
    int connect(const Address&){observe("connect");hook("connect");return connect_result;}
    void clean(){observe("clean");hook("clean");}
    size_t get_out_buffer_length(){observe("output-length");return output_length;}
    ssize_t sendto(const Address&,const char*,size_t length,int flags){observe("sendto:"+std::to_string(length)+":"+std::to_string(flags));return datagram_result;}
};
static int swoole_event_add(Socket*,int){observe("event-add");hook("event");return event_result;}
static int swoole_event_write(Socket*,const char*,size_t length){observe("event-write:"+std::to_string(length));hook("write");return write_result;}
// DECLARATIONS
namespace BODY_NAMESPACE {
struct Client {
    Socket *socket=nullptr;Address server_addr;
    bool async=false,wait_dns=false,active=false,open_ssl=false,onerror_called=false,high_watermark=false;
    int sock_flags_=9;size_t buffer_high_watermark=4;
    std::function<void(Client*)> onReceive,onError,onConnect,onBufferFull;
    bool *destroyed=nullptr;
    ~Client(){observe("destroy");*destroyed=true;}
    void set_timeout(double n){observe("timeout:"+std::to_string(n));hook("timeout");}
    void enable_dtls(){observe("dtls");hook("dtls");}
    int ssl_handshake(){observe("ssl");hook("ssl");return ssl_result;}
    int close(){observe("close");hook("close");return -1;}
};
static int Client_inet_addr(Client*,const char*host,int port){observe("address:"+std::string(host)+":"+std::to_string(port));hook("address");return address_result;}
static int Client_dns_lookup(Client*){observe("dns");hook("dns");return dns_result;}
static void execute_onConnect(Client*cli){observe("on-connect");cli->onConnect(cli);}
// ACTUAL_BODY
static std::string run(unsigned bits,unsigned scenario,unsigned outcome,unsigned mode,int udp_connect){
    effects.clear();effect_hook={};bool destroyed=false;Socket first,second;second.fd=99;first.output_length=outcome%3?3:9;second.output_length=9;
    first.socket_type=bits&64?SW_SOCK_UNIX_DGRAM:1;
    auto *cli=new Client;cli->destroyed=&destroyed;cli->socket=&first;cli->async=bits&1;cli->wait_dns=bits&8;cli->open_ssl=bits&32;cli->high_watermark=bits&512;
    address_result=scenario==1?-1:0;connect_result=int(outcome%3)-1;bind_result=outcome%2?-1:0;event_result=outcome<3?-1:7;ssl_result=int(outcome%3)-1;dns_result=outcome<3?-1:9;write_result=outcome%2?-1:0;last_error=outcome>=3?SW_ERROR_OUTPUT_BUFFER_OVERFLOW:73;
    probe=[&]{if(destroyed)return std::string("deleted");std::ostringstream s;s<<cli->async<<cli->wait_dns<<cli->active<<cli->open_ssl<<cli->onerror_called<<cli->high_watermark<<":"<<cli->sock_flags_<<":"<<first.removed<<":"<<second.removed<<":"<<(cli->socket==&second)<<":"<<first.info.addr.un.sun_path;return s.str();};
    auto callback=[&](Client*c,const std::string&name){observe("callback:"+name);
        if(scenario==2){c->open_ssl=false;c->close();}
        if(scenario==3)throw std::runtime_error("native callback");
        // Connect is followed by another original Client observation; deleting
        // there is an existing native undefined path, not a parity fixture.
        if(scenario==4){if(name=="connect")c->open_ssl=false;else delete c;}
    };
    if(bits&2)cli->onReceive=[](Client*){};
    if(bits&4)cli->onError=[&](Client*c){callback(c,"error");};
    if(bits&16)cli->onConnect=[&](Client*c){callback(c,"connect");};
    if(bits&256)cli->onBufferFull=[&](Client*c){callback(c,"full");};
    effect_hook=[&](const std::string&name){
        if(scenario==5&&name=="write"){cli->socket=&second;cli->high_watermark=true;}
        if(scenario==6&&name=="close"){cli->onError={};cli->async=false;}
        if(scenario==7&&name=="dtls"){cli->async=false;cli->onConnect={};}
        if(scenario==8&&name=="timeout"){cli->async=!cli->async;cli->wait_dns=!cli->wait_dns;cli->onReceive={};}
        if(scenario==9&&name=="buffer-size"){cli->socket=&second;cli->open_ssl=false;}
    };
    ssize_t result=17;std::string exception;
    try{if(mode==0)result=Client_udp_connect(cli,"host",123,bits&128?0.5:0.0,udp_connect);else result=Client_tcp_send_async(cli,"data",4,123);}catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream output;output<<result<<":"<<exception<<":"<<probe();for(const auto&item:effects)output<<"|"<<item;
    if(!destroyed)delete cli;probe={};effect_hook={};return output.str();
}
static ssize_t datagram(ssize_t result,size_t length){Socket socket;bool destroyed=false;Client cli;cli.destroyed=&destroyed;cli.socket=&socket;datagram_result=result;return Client_udp_send(&cli,"data",length,123);}
} // BODY_NAMESPACE
// DRIVER
