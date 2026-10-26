#pragma once
#include "swoole_rs_httpbindings.h"
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cerrno>
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <unordered_map>
#include <stdexcept>
#include <strings.h>
#define SW_STRL(s) s,sizeof(s)-1
#define SW_ZSTR_KNOWN(s) s
#define SW_ZEND_STR_MASTER_TIME "master_time"
#define SW_OK 0
#define SW_ERR -1
#define SW_LOG_TRACE 1
#define SW_TRACE_SERVER 2
#define SW_ERROR_SESSION_NOT_EXIST 3
#define SW_HTTP_BAD_REQUEST_PACKET "BAD\r\n"
#define HTTP_REQUEST 1
#define HPE_OK 0
#define UNEXPECTED(x) (x)
#define sw_unlikely(x) (x)
using zend_long=long;
struct HttpContext;struct Server;struct AcceptServer;
struct Exit{};
struct Oracle {
 uint32_t config=0;size_t fail=SIZE_MAX;long cid=0;int accept_error=0;bool accept_connection=false;AcceptServer*accept_server=nullptr;std::vector<std::string>trace;std::set<HttpContext*>live;Server*server=nullptr;
 ~Oracle();void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};}
};
extern thread_local Oracle*oracle;
struct zval{std::string value;HttpContext*owner=nullptr;int kind=0;};
using HashTable=zval;
#define Z_ARR_P(p) (p)
#define Z_STRLEN_P(p) ((p)->value.size())
#define Z_STRVAL_P(p) ((p)->value.c_str())
namespace zend{struct Callable{int id;};}
namespace WebSocket{enum{STATUS_CONNECTION=1,STATUS_HANDSHAKE=2};}
struct Connection{int websocket_status=0;bool http2_stream=false;long last_recv_time=100;};
struct ListenPort{bool open_http_protocol=false,open_websocket_protocol=false;};
struct RecvData{struct{long fd=42;int server_fd=9;}info;};
struct llhttp_t{int error=0;void*data=nullptr;};
struct Server {
 Connection conn;ListenPort port;bool found=false;
 Connection*get_connection_verify_no_ssl(long fd){oracle->event("connection:"+std::to_string(fd));return found?&conn:nullptr;}
 ListenPort*get_port_by_server_fd(int fd){oracle->event("port:"+std::to_string(fd));return &port;}
};
struct HttpContext {
 struct{zval data,object,server;zval*zobject=&object,*zserver=&server;zval&zdata=data;}request;
 struct{zval object;zval*zobject=&object;}response;
 llhttp_t parser;bool completed=false,keepalive=false,upgrade=false;int refs=2;
 void*private_data_2=nullptr;bool(*onBeforeRequest)(HttpContext*)=nullptr;
 bool(*send)(HttpContext*,const char*,size_t)=nullptr;bool(*close)(HttpContext*)=nullptr;
 HttpContext(){request.object.owner=this;request.object.kind=1;response.object.owner=this;response.object.kind=2;}
 void init(Server*);
 size_t parse(const char*,size_t);
};
inline Oracle::~Oracle(){for(auto*p:live)delete p;}
inline bool native_send(HttpContext*,const char*s,size_t n){oracle->event("send:"+std::string(s,n));return true;}
inline bool native_close(HttpContext*ctx){oracle->event("close");if(oracle->config&(1u<<8))ctx->parser.error=!ctx->parser.error;return true;}
inline void HttpContext::init(Server*){oracle->event("init");send=native_send;close=native_close;keepalive=true;}
inline size_t HttpContext::parse(const char*,size_t n){oracle->event("parse");parser.error=(oracle->config>>6)&1;completed=oracle->config&(1u<<7);return n? n-1:0;}
inline HttpContext*swoole_http_context_new(long fd){oracle->event("new:"+std::to_string(fd));auto*p=new HttpContext;oracle->live.insert(p);return p;}
inline void php_swoole_get_recv_data(Server*,zval*z,RecvData*){oracle->event("receive-data");z->value="request-bytes";}
inline void swoole_llhttp_parser_init(llhttp_t*p,int,void*ctx){oracle->event("parser-init");p->data=ctx;}
inline const char*llhttp_get_error_reason(llhttp_t*){oracle->event("reason");return "parse-error";}
inline void emit_log(const char*prefix,const char*fmt,va_list args){char b[512];vsnprintf(b,sizeof(b),fmt,args);oracle->event(std::string(prefix)+b);}
inline void swoole_error_log(int,int,const char*fmt,...){va_list args;va_start(args,fmt);emit_log("error:",fmt,args);va_end(args);}
inline void swoole_trace_log(int,const char*fmt,...){va_list args;va_start(args,fmt);emit_log("trace:",fmt,args);va_end(args);}
inline void swoole_notice(const char*fmt,...){va_list args;va_start(args,fmt);emit_log("notice:",fmt,args);va_end(args);}
enum{SW_SERVER_CB_onRequest=1,SW_SERVER_CB_onMessage=2,SW_SERVER_CB_onHandshake=3};
inline bool php_swoole_server_isset_callback(Server*,ListenPort*p,int kind){oracle->event("isset:"+std::to_string(kind));bool result=oracle->config&(1u<<(kind==1?3:4));if(kind==1 && (oracle->config&(1u<<16)))p->open_websocket_protocol=!p->open_websocket_protocol;return result;}
inline zend::Callable*php_swoole_server_get_callback(Server*,int fd,int kind){oracle->event("get-callback:"+std::to_string(fd)+":"+std::to_string(kind));static zend::Callable request{1},handshake{3};return oracle->config&(1u<<(kind==3?11:12))?(kind==3?&handshake:&request):nullptr;}
inline int php_swoole_server_onReceive(Server*,RecvData*){oracle->event("raw");return 31;}
inline int swoole_websocket_onMessage(Server*,RecvData*){oracle->event("websocket");return -3;}
inline int swoole_http2_server_onReceive(Server*,Connection*,RecvData*){oracle->event("http2");return 77;}
inline void swoole_websocket_onHandshake(Server*,ListenPort*,HttpContext*){oracle->event("default-handshake");}
inline void swoole_websocket_onRequest(HttpContext*){oracle->event("default-request");}
inline void swoole_http_server_populate_ip_and_port(Server*,zval*,Connection*,long,bool){oracle->event("populate");}
inline void http_server_add_server_array(zval*,const char*key,zend_long n){oracle->event("server:"+std::string(key)+":"+std::to_string(n));}
enum swGlobalHookType{PHP_SWOOLE_HOOK_BEFORE_REQUEST=1};
inline bool swoole_isset_hook(swGlobalHookType){oracle->event("hook-probe");return oracle->config&(1u<<9);}
inline void swoole_call_hook(swGlobalHookType,HttpContext*ctx){oracle->event("hook");if(oracle->config&(1u<<10))oracle->server->conn.websocket_status=WebSocket::STATUS_CONNECTION;if(oracle->config&(1u<<13))ctx->onBeforeRequest=nullptr;}
inline bool swoole_http_server_onBeforeRequest(HttpContext*){oracle->event("before");return oracle->config&(1u<<14);}
inline void http_server_process_request(const Server*,zend::Callable*cb,HttpContext*ctx){oracle->event("process:"+std::to_string(cb->id));if(ctx->private_data_2!=cb)throw std::runtime_error("callback identity lost");}
inline void zval_ptr_dtor(zval*z){oracle->event("dtor:"+std::to_string(z->kind));auto*ctx=z->owner;if(!--ctx->refs){oracle->live.erase(ctx);delete ctx;}}
#define SERVER_DECL(ns) namespace ns{int php_swoole_http_server_onReceive(Server*,RecvData*);}
SERVER_DECL(upstream_server)
SERVER_DECL(candidate_server)
struct RouteContext{struct{const char*path;size_t path_len;}request;};
#define HANDLER_DECL(ns) namespace ns{struct HandlerServer{zend::Callable*default_handler=nullptr;std::unordered_map<std::string,zend::Callable*>handlers;zend::Callable*get_handler(const RouteContext*)const;};}
HANDLER_DECL(upstream_server)
HANDLER_DECL(candidate_server)

#define SW_ERROR_SSL_BAD_CLIENT 4001
#define SW_ACCEPT_RETRY_TIME 1
#define E_WARNING 2
#define ZEND_THIS nullptr
#define RETURN_FALSE do{oracle->event("return-false");return;}while(0)
struct AcceptSocket{int errCode=0;const char*errMsg="fake-error";AcceptSocket*accept();};
struct AcceptServer{bool running=true;};
inline AcceptSocket*AcceptSocket::accept(){oracle->event("accept");oracle->accept_server->running=false;errCode=oracle->accept_error;return oracle->accept_connection?this:nullptr;}
struct Callback{zval value;zval*ptr(){return &value;}};
struct PHPCoroutine{static long create(void*,int,zval*,zval*){oracle->event("create-coroutine");return oracle->cid;}};
struct System{static void sleep(int){oracle->event("sleep");}};
inline void php_swoole_init_socket_object(zval*,AcceptSocket*){oracle->event("socket-object");}
inline void zval_dtor(zval*){oracle->event("socket-dtor");}
inline void http_server_coro_set_error(void*,AcceptSocket*){oracle->event("set-error");}
inline void php_swoole_fatal_error(int,const char*fmt,...){va_list args;va_start(args,fmt);emit_log("warning:",fmt,args);va_end(args);}
namespace upstream_server{void call_accept(AcceptSocket*,AcceptServer*);}
namespace candidate_server{void call_accept(AcceptSocket*,AcceptServer*);}
