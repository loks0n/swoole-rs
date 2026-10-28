#include <cstdint>
#include <cerrno>
#include <string>
#include <vector>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include "swoole_rs_clients.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_READY 1
#define SW_WAIT 2
#define SW_EVENT_WRITE 2
#define SW_SOCKS5_STATE_HANDSHAKE 1
#define SW_SOCKS5_STATE_READY 2
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void(const std::string&)> effect_hook;
static int blocking_result,nonblocking_result,async_result,async_errno,async_calls,address_result,send_result,receive_result,ssl_result,event_result,dns_result;
static bool handshake_ok,timer_ok,first_interrupt;
static void observe(const std::string&what){effects.push_back(what+":"+(probe?probe():""));}
static void hook(const std::string&name){if(effect_hook)effect_hook(name);}
#define swoole_warning(...) observe("callback-warning")
struct String;
static std::vector<String*> allocations;
struct String {
    char bytes[128]="proxy-response";char *str=bytes;size_t size=16,length=0;
    String()=default;
    explicit String(uint32_t requested):size(requested){observe("allocate:"+std::to_string(requested));allocations.push_back(this);}
};
static String transfer_buffer;
static String *sw_tg_buffer(){observe("transfer-buffer");return &transfer_buffer;}
struct Address {};
struct Timer {};
struct TimerNode {};
static TimerNode timer_node;
struct Proxy {
    int state=0;char buf[16]="socks";
    size_t pack_negotiate_request(){observe("socks-pack");return 5;}
    size_t pack(String*,const std::string&host){observe("http-pack:"+host);return 4;}
    bool handshake(String*){observe("http-handshake");hook("handshake");return handshake_ok;}
};
using Socks5Proxy=Proxy;
struct ProxyPtr {
    Proxy *ptr=nullptr;
    Proxy *get()const{return ptr;}
    Proxy *operator->()const{return ptr;}
    operator bool()const{return ptr!=nullptr;}
    bool operator!=(std::nullptr_t)const{return ptr!=nullptr;}
};
struct Socket {
    bool removed=false;uint32_t buffer_size=101;
    void set_kernel_timeout(double n){observe("kernel-timeout:"+std::to_string(n));hook("kernel-timeout");}
    int connect_async(const Address&){observe("nonblocking");hook("connect");return nonblocking_result;}
    int connect_sync(const Address&){observe("blocking");hook("connect");return blocking_result;}
    int connect(const Address&){observe("async-connect");hook("connect");if(first_interrupt&&async_calls++==0){errno=EINTR;return -1;}errno=async_errno;return async_result;}
};
static int swoole_event_add(Socket*,int){observe("event-add");hook("event");return event_result;}
template<typename Function,typename Client>static TimerNode *swoole_timer_add(double timeout,bool,Function,Client*){observe("timer-add:"+std::to_string(timeout));hook("timer");return timer_ok?&timer_node:nullptr;}
// DECLARATIONS
namespace BODY_NAMESPACE {
struct Client {
    // The patched bodies reach the flags through the Client accessors (#447).
    bool is_active() const{return active;} void set_active(bool v){active=v;}
    Socket *socket=nullptr;String *buffer=nullptr;Address server_addr;
    ProxyPtr socks5_proxy,http_proxy;
    bool active=false,async_connect=false,wait_dns=false,onerror_called=false;
    bool open_ssl=false;uint32_t input_buffer_size=16,buffer_high_watermark=0;
    TimerNode *timer=nullptr;bool *destroyed=nullptr;
    std::function<void(Client*)> onConnect,onError,onReceive,onClose,onBufferFull;
    int handshake_calls=0;
    ~Client(){observe("destroy");*destroyed=true;}
    void set_timeout(double value){observe("timeout:"+std::to_string(value));hook("timeout");}
    ssize_t send(const char*bytes,size_t length,int=0){observe("send:"+std::string(bytes,length));hook("send");return send_result;}
    ssize_t recv(char*,size_t size,int){observe("recv:"+std::to_string(size));hook("recv");return receive_result;}
    bool socks5_handshake(const char*,ssize_t size){observe("socks-handshake:"+std::to_string(size));if(++handshake_calls==2)socks5_proxy->state=SW_SOCKS5_STATE_READY;hook("handshake");return handshake_ok;}
    std::string get_http_proxy_host_name(){observe("proxy-host");return "target";}
    int ssl_handshake(){observe("ssl");hook("ssl");return ssl_result;}
    int close(){observe("close");hook("close");return -1;}
};
static int Client_inet_addr(Client*,const char*host,int port){observe("address:"+std::string(host)+":"+std::to_string(port));hook("address");return address_result;}
static int Client_dns_lookup(Client*){observe("dns");hook("dns");return dns_result;}
static void Client_onTimeout(Timer*,TimerNode*){}
// ACTUAL_BODY
static std::string run(unsigned bits,unsigned scenario,unsigned outcome,unsigned mode){
    effects.clear();effect_hook={};allocations.clear();async_calls=0;bool destroyed=false;
    transfer_buffer.length=0;Socket first,second;Proxy socks,http,replacement;String existing;
    auto *cli=new Client;cli->destroyed=&destroyed;cli->socket=&first;
    cli->socks5_proxy.ptr=bits&1?&socks:nullptr;cli->http_proxy.ptr=bits&2?&http:nullptr;cli->open_ssl=bits&4;
    cli->buffer=bits&16?&existing:nullptr;cli->buffer_high_watermark=bits&64?7:0;cli->wait_dns=bits&128;
    blocking_result=int(outcome%3)-1;nonblocking_result=int(outcome%3);send_result=int(outcome/3)-1;receive_result=int(outcome%3)-1;
    handshake_ok=outcome>=3;ssl_result=outcome<3?-1:0;timer_ok=bits&512;
    async_result=outcome%3==1?0:-1;async_errno=outcome%3==0?EINPROGRESS:ECONNREFUSED;
    event_result=scenario&1?-1:7;dns_result=scenario&1?-1:9;address_result=scenario==1?-1:0;first_interrupt=scenario==5;
    probe=[&]{if(destroyed)return std::string("deleted");std::ostringstream s;
        s<<cli->active<<cli->async_connect<<cli->wait_dns<<cli->onerror_called<<cli->open_ssl<<":"<<first.removed<<":"<<second.removed<<":"<<socks.state<<":"<<http.state<<":"<<replacement.state<<":"<<cli->buffer_high_watermark<<":"<<(cli->buffer!=nullptr)<<":"<<(cli->timer!=nullptr)<<":"<<(cli->socket==&second)<<":"<<transfer_buffer.length;return s.str();};
    auto callback=[&](Client*c){observe("callback");if(scenario==3)throw std::runtime_error("native callback");if(scenario==4)delete c;};
    cli->onConnect=callback;cli->onError=callback;cli->onReceive=callback;if(bits&8)cli->onClose=callback;if(bits&32)cli->onBufferFull=callback;
    effect_hook=[&](const std::string&name){
        if(scenario==2&&name=="close")cli->onError={};
        if(scenario==5){
            if(name=="timeout"){cli->buffer=nullptr;cli->buffer_high_watermark=0;}
            if(name=="send"){cli->socket=&second;cli->open_ssl=false;}
            if(name=="handshake"&&cli->http_proxy)cli->http_proxy.ptr=&replacement;
        }
    };
    int returned=17;std::string exception;
    try{if(mode==2)returned=Client_tcp_connect_async(cli,"host",123,bits&256?0.5:0.0,0);
        else returned=Client_tcp_connect_sync(cli,"host",123,bits&256?0.5:0.0,mode==1);
    }catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream output;output<<returned<<":"<<exception<<":"<<probe();for(const auto&item:effects)output<<"|"<<item;
    if(!destroyed)delete cli;probe={};effect_hook={};for(auto *allocation:allocations)delete allocation;allocations.clear();return output.str();
}
} // BODY_NAMESPACE
// DRIVER
