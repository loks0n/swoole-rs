#include <cstdint>
#include <string>
#include <vector>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include "swoole_rs_clients.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_SSL_STATE_WAIT_STREAM 1
#define SW_SSL_STATE_READY 2
#define SW_SOCKS5_STATE_WAIT 1
#define SW_SOCKS5_STATE_HANDSHAKE 2
#define SW_HTTP_PROXY_STATE_WAIT 1
#define SW_EVENT_READ 1
#define SOL_SOCKET 1
#define SO_ERROR 1
#define SW_ERROR_SSL_HANDSHAKE_FAILED 900
#define SW_TRACE_HTTP_CLIENT 0
#define swoole_trace_log(...) ((void)0)
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void()> effect_hook;
static int last_error,handshake_result,handshake_state,writable_result,option_result,option_error,send_result;
static void observe(const std::string&what){effects.push_back(what+":"+(probe?probe():""));}
static int swoole_get_last_error(){observe("get-error");return last_error;}
static void swoole_set_last_error(int n){observe("set-error:"+std::to_string(n));last_error=n;}
#define swoole_sys_warning(...) observe("option-warning")
struct Buffer {char bytes[16]="http";char *str=bytes;};
static Buffer proxy_buffer;
static Buffer *sw_tg_buffer(){observe("get-buffer");return &proxy_buffer;}
struct Proxy {
    int state=0;char buf[16]="socks";
    size_t pack_negotiate_request(){observe("socks-pack");return 5;}
    size_t pack(Buffer*,const std::string&host){observe("http-pack:"+host);return 4;}
};
struct Socket {
    void *object=nullptr;int ssl_state=0,ssl_want_read=0;size_t output_length=0;
    int get_option(int,int,int *out){observe("option");*out=option_error;return option_result;}
    size_t get_out_buffer_length(){observe("buffer-length");return output_length;}
};
struct Event {Socket *socket;int fd=123;};
struct Reactor {static int _writable_callback(Reactor*,Event*){observe("writable");if(effect_hook)effect_hook();return writable_result;}};
static int swoole_event_set(Socket*,int){observe("read-interest");if(effect_hook)effect_hook();return 0;}
// DECLARATIONS: inserted once for each actual native/selected body.
namespace BODY_NAMESPACE {
struct Client {
    // The patched bodies reach the flags through the Client accessors (#447).
    bool is_active() const{return active;} void set_active(bool v){active=v;}
    Socket *socket=nullptr;bool active=false,open_ssl=false,high_watermark=false;
    size_t buffer_low_watermark=4;Proxy *socks5_proxy=nullptr,*http_proxy=nullptr;
    std::function<void(Client*)> onBufferEmpty,onError,onConnect;
    bool *destroyed=nullptr;
    ~Client(){observe("destroy");*destroyed=true;}
    int ssl_handshake(){observe("handshake");socket->ssl_state=handshake_state;return handshake_result;}
    std::string get_http_proxy_host_name(){observe("proxy-host");return "target";}
    int send(const char *bytes,size_t length,int){observe("send:"+std::string(bytes,length));return send_result;}
    int close(){observe("close");return 0;}
};
static void execute_onConnect(Client *cli){observe("connect");cli->onConnect(cli);}
// ACTUAL_BODY
static std::string run(unsigned bits,unsigned scenario,unsigned outcome){
    effects.clear();effect_hook={};last_error=73;bool destroyed=false;
    Socket first,second;first.ssl_state=bits&8?SW_SSL_STATE_READY:(bits&4?SW_SSL_STATE_WAIT_STREAM:0);
    second.ssl_state=SW_SSL_STATE_READY;first.ssl_want_read=bits&16;first.output_length=bits&2048?4:5;
    Proxy socks,http;socks.state=bits&256?SW_SOCKS5_STATE_WAIT:0;http.state=bits&1024?SW_HTTP_PROXY_STATE_WAIT:0;
    auto *cli=new Client;cli->destroyed=&destroyed;cli->socket=&first;first.object=second.object=cli;
    cli->active=bits&1;cli->open_ssl=bits&2;cli->high_watermark=bits&64;
    cli->socks5_proxy=bits&128?&socks:nullptr;cli->http_proxy=bits&512?&http:nullptr;
    handshake_result=outcome%3==0?-1:0;handshake_state=outcome%3==1?SW_SSL_STATE_READY:0;
    writable_result=outcome/3==0?-1:0;option_result=outcome/3==1?-1:0;option_error=outcome/3==2?111:0;
    send_result=scenario==4?-1:7;
    probe=[&]{if(destroyed)return std::string("deleted");std::ostringstream s;
        s<<cli->active<<cli->open_ssl<<cli->high_watermark<<":"<<first.ssl_state<<":"<<socks.state<<":"<<http.state<<":"<<(cli->socket==&second);return s.str();};
    auto callback=[&](Client*c){observe("callback");
        if(scenario==1){c->active=false;c->close();}
        if(scenario==2)throw std::runtime_error("native callback");
        if(scenario==3)delete c;
    };
    if(bits&32)cli->onBufferEmpty=callback;
    cli->onConnect=callback;cli->onError=callback;
    if(scenario==4)effect_hook=[&]{cli->socket=&second;cli->high_watermark=true;cli->open_ssl=false;cli->socks5_proxy=nullptr;};
    Event event{&first,123};Reactor reactor;int result=17;std::string exception;
    try{result=Client_onWrite(&reactor,&event);}catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream output;output<<result<<":"<<exception<<":"<<last_error<<":"<<probe();
    for(const auto&item:effects)output<<"|"<<item;
    if(!destroyed)delete cli;probe={};effect_hook={};return output.str();
}
} // BODY_NAMESPACE
// DRIVER
