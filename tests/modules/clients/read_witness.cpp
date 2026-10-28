#include <cstdint>
#include <cerrno>
#include <string>
#include <vector>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <memory>
#include <iostream>
#include "swoole_rs_clients.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_ERROR 1
#define SW_CLOSE 2
#define SW_WAIT 3
#define SW_HTTP_PROXY_STATE_READY 2
#define SW_SOCKS5_STATE_READY 2
#define SW_SSL_STATE_READY 2
#define SW_ERROR_HTTP_PROXY_HANDSHAKE_ERROR 900
#define SW_ERROR_SOCKS5_HANDSHAKE_FAILED 901
#define SW_ERROR_SSL_HANDSHAKE_FAILED 902
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void(const std::string&)> effect_hook;
static int last_error,receive_result,handshake_result,error_kind,close_result;
static bool handshake_ok,handshake_ready;
static void observe(const std::string&what){effects.push_back(what+":"+(probe?probe():""));}
static void hook(const std::string&name){if(effect_hook)effect_hook(name);}
static void swoole_set_last_error(int n){observe("set-error:"+std::to_string(n));last_error=n;}
#define swoole_sys_warning(...) observe("read-warning")
struct Buffer {
    char bytes[32]="abcdefghijklmnopqrstuvwxyz";char *str=bytes;size_t length=2,size=16;int identity=0;
    void clear(){observe("clear:"+std::to_string(identity));length=0;hook("clear");}
};
struct Proxy {
    int state=0;
    bool handshake(Buffer*){observe("http-handshake");hook("handshake");return handshake_ok;}
};
struct Socket {
    void *object=nullptr;int ssl_state=0,removed=0;
    ssize_t recv(char *out,size_t capacity,int){observe("recv:"+std::to_string(capacity)+":"+std::string(out,2));errno=19;hook("receive");return receive_result;}
    int catch_read_error(int error){observe("catch:"+std::to_string(error));return error_kind;}
};
struct Protocol {
    ssize_t recv_with_eof_protocol(Socket*,Buffer*){observe("eof");hook("protocol");return receive_result;}
    ssize_t recv_with_length_protocol(Socket*,Buffer*){observe("length");hook("protocol");return receive_result;}
};
struct Event {Socket *socket;int fd=123;};
struct Reactor {};
// DECLARATIONS
namespace BODY_NAMESPACE {
struct Client {
#ifdef SELECTED_STATE
    // The selected Client's flags are Rust's (#447); scenarios set and read them the same way.
    std::unique_ptr<swr_v1_clients_state,decltype(&swr_v1_clients_state_free)> state_{swr_v1_clients_state_new(true),swr_v1_clients_state_free};
    bool flag(uint32_t f) const{return swr_v1_clients_flag(state_.get(),f);}
    void set_flag(uint32_t f,bool v){swr_v1_clients_set_flag(state_.get(),f,v);}
#else
    bool active=true,closed=false;
    bool flag(uint32_t f) const{return f==SWR_CLIENTS_CLOSED?closed:active;}
    void set_flag(uint32_t f,bool v){(f==SWR_CLIENTS_CLOSED?closed:active)=v;}
#endif
    bool is_active() const{return flag(SWR_CLIENTS_ACTIVE);} void set_active(bool v){set_flag(SWR_CLIENTS_ACTIVE,v);} bool is_closed() const{return flag(SWR_CLIENTS_CLOSED);}
    Socket *socket=nullptr;Buffer *buffer=nullptr;Protocol protocol;
    bool open_ssl=false,open_eof_check=false,open_length_check=false,remove_delay=false;
    Proxy *http_proxy=nullptr,*socks5_proxy=nullptr;
    std::function<void(Client*)> onError,onConnect;
    std::function<void(Client*,const char*,size_t)> onReceive;
    bool *destroyed=nullptr;
    ~Client(){observe("destroy");*destroyed=true;}
    bool socks5_handshake(const char *bytes,size_t size){observe("socks-handshake:"+std::to_string(size)+":"+std::string(bytes,2));if(handshake_ready)socks5_proxy->state=SW_SOCKS5_STATE_READY;hook("handshake");return handshake_ok;}
    int ssl_handshake(){observe("ssl-handshake");if(handshake_ready)socket->ssl_state=SW_SSL_STATE_READY;hook("handshake");return handshake_result;}
    int close(){observe("close");set_flag(SWR_CLIENTS_CLOSED,true);return close_result;}
    int sleep(){observe("sleep");hook("sleep");return -1;}
};
static void execute_onConnect(Client *cli){observe("connect");cli->onConnect(cli);}
// ACTUAL_BODY
static std::string run(unsigned bits,unsigned scenario,unsigned outcome){
    effects.clear();effect_hook={};last_error=73;bool destroyed=false;
    Socket first,second;first.ssl_state=bits&32?SW_SSL_STATE_READY:0;first.removed=bits&512;second.removed=1;
    Buffer buffer,alternate;alternate.identity=1;alternate.length=3;
    Proxy http,socks,replacement;http.state=bits&2?SW_HTTP_PROXY_STATE_READY:0;socks.state=bits&8?SW_SOCKS5_STATE_READY:0;
    auto *cli=new Client;cli->destroyed=&destroyed;cli->socket=&first;first.object=second.object=cli;cli->buffer=&buffer;
    cli->http_proxy=bits&1?&http:nullptr;cli->socks5_proxy=bits&4?&socks:nullptr;cli->open_ssl=bits&16;
    cli->open_eof_check=bits&64;cli->open_length_check=bits&128;cli->set_flag(SWR_CLIENTS_CLOSED,bits&256);cli->remove_delay=bits&1024;
    receive_result=outcome%3==0?-1:(outcome%3==1?0:2);handshake_result=outcome<3?-1:0;
    handshake_ok=outcome>=3;handshake_ready=outcome>=6;error_kind=1+outcome/3;close_result=scenario&1?-1:7;
    probe=[&]{if(destroyed)return std::string("deleted");std::ostringstream s;
        s<<cli->is_active()<<cli->open_ssl<<cli->is_closed()<<cli->remove_delay<<":"<<first.ssl_state<<":"<<first.removed<<":"<<http.state<<":"<<socks.state<<":"<<replacement.state<<":"<<buffer.length<<":"<<alternate.length<<":"<<(cli->socket==&second)<<":"<<(cli->buffer==&alternate);return s.str();};
    auto callback=[&](Client*c){observe("callback");
        if(scenario==1){c->set_active(false);c->close();}
        if(scenario==2)throw std::runtime_error("native callback");
        if(scenario==3)delete c;
    };
    cli->onConnect=callback;
    if(outcome&1)cli->onError=callback;
    cli->onReceive=[&](Client*c,const char*bytes,size_t size){observe("receive-callback:"+std::string(bytes,size));callback(c);};
    effect_hook=[&](const std::string&name){
        if(scenario==4&&name=="receive")cli->open_ssl=false;
        if(scenario==5&&name=="protocol"){cli->socket=&second;cli->remove_delay=true;}
        if(scenario==6&&name=="handshake"){cli->buffer=&alternate;cli->open_ssl=false;if(cli->http_proxy)cli->http_proxy=&replacement;}
        if(scenario==7){if(name=="protocol"){cli->set_flag(SWR_CLIENTS_CLOSED,true);first.removed=0;}if(name=="sleep")cli->remove_delay=true;}
    };
    Event event{&first,123};Reactor reactor;int result=17;std::string exception;
    try{result=Client_onStreamRead(&reactor,&event);}catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream output;output<<result<<":"<<exception<<":"<<last_error<<":"<<probe();
    for(const auto&item:effects)output<<"|"<<item;
    if(!destroyed)delete cli;probe={};effect_hook={};return output.str();
}
} // BODY_NAMESPACE
// DRIVER
