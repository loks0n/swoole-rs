/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <cerrno>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#define SW_LOOP_N(n) for(decltype(n) i=0;i<n;i++)
#define UNEXPECTED(x) (x)
#define ZVAL_OBJ(z,o) ((z)->object=(o))
#define Z_OBJCE_P(z) (z)
#define SW_Z8_OBJ_P(z) (z)
#define SW_ZSTR_KNOWN(z) 0
#define ZEND_STRL(z) z,sizeof(z)-1
// DECLARATIONS
namespace BODY_NAMESPACE {
constexpr int SW_HTTP_RESPONSE_INIT_SIZE=8192,HTTP_ESTATUS_CONNECT_FAILED=-1,HTTP_ESTATUS_SERVER_RESET=-2,SW_TIMEOUT_CONNECT=1,SW_EVENT_RDWR=3;
struct Client;struct Socket;struct zend_object {Socket *socket;};struct zval{zend_object *object=nullptr;};
static Client *active;static unsigned bits,mutation;static int fail_at,event_count;static std::ostringstream trace;
static void event(const std::string&);static void change(unsigned);
struct String {explicit String(int){event("allocate-body");}};
struct Socket {
 int errCode=111,close_wait=0,id=0;const char *errMsg="native-error";double timeout=0;std::function<void(Socket*)> dtor;
 bool enable_ssl_encrypt(){event("ssl:"+std::to_string(id));change(1);return !(bits&16);}
 void set_timeout(double value,int){event("timeout:"+std::to_string(value)+":"+std::to_string(id));timeout=value;change(2);}
 void set_resolve_context(void*){event("resolve-context:"+std::to_string(id));change(3);}
 void set_dtor(std::function<void(Socket*)> fn){event("set-dtor:"+std::to_string(id));dtor=std::move(fn);}
 void set_buffer_allocator(int){event("allocator:"+std::to_string(id));}
 bool connect(const std::string&,int){event("connect:"+std::to_string(id));change(4);return !(bits&32);}
 bool check_liveness(){event("liveness:"+std::to_string(id));change(5);return bits&64;}
 void check_bound_co(int){event("bound:"+std::to_string(id));change(6);}
 Socket *get_socket(){event("get-socket:"+std::to_string(id));return this;}
 bool close();
};
using SocketImpl=Socket;namespace network {struct Socket {static constexpr double default_connect_timeout=7.25;};}
static Socket sockets[3];static zend_object objects[3];static int swoole_http_client_coro_ce;
struct Client {
 Socket *socket=nullptr;String *body=nullptr;zval zsocket,object;zval *zobject=&object;
 bool ssl=false,websocket=true,accept_websocket_compression=true,in_callback=false;double connect_timeout=0;
 unsigned char max_retries=0;int socket_type=0,resolve_context_=0;std::string host="localhost";int port=80,error=0,status=0;
 bool connect();bool keep_liveness();bool close(const bool should_be_reset=true);
 void set_error(int code,const char*,int state){event("set-error:"+std::to_string(code)+":"+std::to_string(state));error=code;status=state;change(7);}
 void apply_setting(zval*,bool){event("apply");change(8);}
 void socket_dtor(){event("socket-dtor");socket=nullptr;}
 void reset(){event("reset");websocket=false;change(9);}
};
static void event(const std::string &name){trace<<name<<":"<<(active->socket?active->socket->id:-1)<<","<<(active->body!=nullptr)<<active->ssl<<active->websocket<<active->accept_websocket_compression<<active->in_callback<<","<<unsigned(active->max_retries)<<';';if(event_count++==fail_at)throw std::runtime_error(name);}
static void change(unsigned point){
 if(mutation!=point)return;
 active->ssl=!active->ssl;active->max_retries=active->max_retries?0:2;active->websocket=!active->websocket;active->connect_timeout=3.5;
 if(point==5)active->socket=nullptr;else if(point==2||point==6||point==7)active->socket=&sockets[2];
}
bool Socket::close(){event("close:"+std::to_string(id));change(10);if(bits&128){if(dtor)dtor(this);else active->socket=nullptr;}return !(bits&256);}
static void php_swoole_check_reactor(){event("reactor");change(11);}
static zend_object *php_swoole_create_socket(int){event("create");errno=23;return bits&8?nullptr:&objects[1];}
static Socket *php_swoole_get_socket(zval*z){event("get-handle");return z->object->socket;}
static zval *sw_zend_read_property_ex(zval*,zval*z,int,int){event("read-settings");return z;}
static int sw_zend_string_allocator(){event("get-allocator");return 1;}
static const char *swoole_strerror(int){event("strerror");return "error";}
static void zend_update_property(int,zval*,const char*,size_t,zval*){event("property-socket");change(12);}
static void zend_update_property_bool(int,zval*,const char*,size_t,int n){event("property-connected:"+std::to_string(n));change(13);}
static void zend_update_property_bool(zval*,zval*,const char*,size_t,int n){event("property-connected:"+std::to_string(n));change(13);}
static void php_swoole_socket_set_error_properties(zval*,Socket*s){event("saved-error:"+std::to_string(s->id));}
// ACTUAL_BODY
static std::string run(unsigned input,unsigned mut,int failure,unsigned operation){
 bits=input;mutation=mut;fail_at=-2;event_count=0;trace.str("");trace.clear();Client cli;active=&cli;
 for(int i=0;i<3;++i){sockets[i]=Socket();sockets[i].id=i;objects[i].socket=&sockets[i];}
 cli.socket=(bits&1)?&sockets[0]:nullptr;cli.ssl=bits&4;cli.in_callback=bits&512;cli.max_retries=(bits>>10)&3;cli.connect_timeout=(bits&4096)?1.5:0;
 if(bits&2)cli.body=new String(1);
 trace.str("");trace.clear();event_count=0;fail_at=failure;bool result=false;std::string exception;
 try{result=operation==0?cli.connect():operation==1?cli.keep_liveness():cli.close(bits&8192);}catch(const std::exception&e){exception=e.what();}
 std::ostringstream answer;answer<<trace.str()<<"|result="<<result<<"|throw="<<exception<<"|state="<<(cli.socket?cli.socket->id:-1)<<','<<(cli.body!=nullptr)<<cli.ssl<<cli.websocket<<cli.accept_websocket_compression<<cli.in_callback<<','<<unsigned(cli.max_retries)<<','<<cli.error<<','<<cli.status;
 for(auto &s:sockets)answer<<"|socket="<<s.id<<','<<s.close_wait<<','<<s.timeout;
 delete cli.body;active=nullptr;return answer.str();
}
}
// DRIVER
