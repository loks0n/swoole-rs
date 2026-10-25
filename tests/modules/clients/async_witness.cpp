/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cctype>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <strings.h>
#include <unordered_set>
#include <vector>
#define PHP_METHOD(c,n) void method_##n(Return *return_value)
#define sw_inline inline
#define UNEXPECTED(a) (a)
#define ZEND_THIS (&object)
#define Z_OBJ_P(z) (z)
#define SW_Z_OBJCE_NAME_VAL_P(z) "WitnessClient"
#define SW_ZSTR_KNOWN(z) 0
#define ZEND_STRL(s) s,sizeof(s)-1
#define ZEND_NUM_ARGS() 4
#define FAILURE -1
#define SUCCESS 0
#define ZVAL_IS_ARRAY(z) ((z)->array)
#define ZEND_PARSE_PARAMETERS_START(a,b) do {
#define ZEND_PARSE_PARAMETERS_END_EX(e) }while(0)
#define Z_PARAM_OPTIONAL
#define Z_PARAM_STRING(p,n) p=args.text.data();n=args.text.size();
#define Z_PARAM_LONG(p) p=args.long_index++==0?args.port:args.flags;
#define Z_PARAM_DOUBLE(p) p=args.timeout;
#define RETURN_FALSE do{return_value->kind=1;return_value->value=false;return;}while(0)
#define RETURN_TRUE do{return_value->kind=1;return_value->value=true;return;}while(0)
// DECLARATIONS
namespace BODY_NAMESPACE {
using zend_long=long;constexpr int E_WARNING=2,E_ERROR=1,SW_CLIENT_CONNECT_TIMEOUT=3,SW_ERROR_DNSLOOKUP_RESOLVE_FAILED=900;
// PINNED_ENUM
struct Return{int kind=0;bool value=false;};struct ClientObject;struct zval{ClientObject*owner=nullptr;bool array=true;};
static void event(const std::string&,bool throwing=true);static void change(unsigned);
static unsigned bits,scenario,mutation;static int fail_at,event_count,callback_id,last_error;static bool cleaning;
static std::ostringstream trace;static std::string event_name;static std::unordered_set<void*>live_callbacks,live_clients,live_containers;
struct CallbackInfo{int id;};
namespace zend {struct Callable{CallbackInfo info;explicit Callable(int id):info{id}{live_callbacks.insert(this);}~Callable(){event("callable-dtor:"+std::to_string(info.id),false);live_callbacks.erase(this);change(3);}CallbackInfo*ptr(){event("callable-ptr:"+std::to_string(info.id));return &info;}};}
struct AsyncClientObject{zend::Callable *onConnect=nullptr,*onReceive=nullptr,*onClose=nullptr,*onError=nullptr,*onBufferFull=nullptr,*onBufferEmpty=nullptr,*onSSLReady=nullptr;zval _zobject;AsyncClientObject(){live_containers.insert(this);}~AsyncClientObject(){event("async-dtor",false);live_containers.erase(this);}};
struct Socket{bool stream=true;bool is_stream(){event("is-stream");return stream;}};
struct Client{
 void*object=nullptr;Socket socket;bool ssl_wait_handshake=false;void(*onConnect)(Client*)=nullptr;void(*onClose)(Client*)=nullptr;void(*onError)(Client*)=nullptr;void(*onBufferFull)(Client*)=nullptr;void(*onBufferEmpty)(Client*)=nullptr;void(*onReceive)(const Client*,const char*,size_t)=nullptr;
 Client(){live_clients.insert(this);}~Client(){event("client-dtor",false);live_clients.erase(this);}Socket*get_socket(){event("get-socket");return &socket;}int connect(const char*,int,double,int);
};
struct ClientObject{Client*cli=nullptr;AsyncClientObject*async=nullptr;int refs=3,property=0;}static state;
static zval object{&state},callback_value{&state},settings{&state};
struct Args{std::string text="host";long port=80,flags=0;double timeout=1.5;unsigned long_index=0;}static args;
static std::vector<zend::Callable*> reserves;
static zend::Callable**slot(ClientObject*o,unsigned n){switch(n){case 1:return &o->async->onConnect;case 2:return &o->async->onReceive;case 3:return &o->async->onClose;case 4:return &o->async->onError;case 5:return &o->async->onBufferFull;case 6:return &o->async->onBufferEmpty;default:return &o->async->onSSLReady;}}
static unsigned mask(){unsigned m=0;if(state.async)for(unsigned i=1;i<=7;++i)if(*slot(&state,i))m|=1u<<(i-1);return m;}
static void event(const std::string&name,bool throwing){if(cleaning)return;trace<<name<<':'<<(state.cli!=nullptr)<<','<<(state.async!=nullptr)<<','<<mask()<<','<<state.refs<<','<<state.property<<';';if(event_count++==fail_at&&throwing){const int saved=errno;std::runtime_error error(name);errno=saved;throw error;}}
static void change(unsigned point){if(cleaning||mutation!=point)return;if(state.async&&(point==1||point==3||point==4)){if(!reserves.empty()){*slot(&state,6)=reserves.back();reserves.pop_back();}}if(point==2)settings.array=!settings.array;if(point==5){last_error=SW_ERROR_DNSLOOKUP_RESOLVE_FAILED;errno=0;}if(point==6)errno=37;}
static ClientObject*php_swoole_client_fetch_object(zval*z){event("fetch-object");return z->owner;}
static zend::Callable*sw_callable_create(zval*){event("create-callable");if(bits&128)return nullptr;return new zend::Callable(callback_id++);}
static void sw_callable_free(zend::Callable*p){event("free-callable:"+std::to_string(p->info.id));assert(live_callbacks.count(p));delete p;}
static int sw_zend_call_function_ex2(void*,CallbackInfo*info,int,zval*,void*){event("invoke:"+std::to_string(info->id));change(4);return bits&256?-1:SUCCESS;}
static std::string format(const char*fmt,va_list ap){char buf[512];vsnprintf(buf,sizeof(buf),fmt,ap);return buf;}
static void php_swoole_fatal_error(int severity,const char*fmt,...){va_list ap;va_start(ap,fmt);auto s=format(fmt,ap);va_end(ap);event("fatal:"+std::to_string(severity)+":"+s);change(6);}
static void php_swoole_error(int severity,const char*fmt,...){va_list ap;va_start(ap,fmt);auto s=format(fmt,ap);va_end(ap);event("warning:"+std::to_string(severity)+":"+s);change(6);}
static void php_swoole_sys_error(int severity,const char*fmt,...){va_list ap;va_start(ap,fmt);auto s=format(fmt,ap);va_end(ap);event("sys-error:"+std::to_string(severity)+":"+s);change(6);}
static void zend_update_property(int,zval*,const char*key,size_t,zval*){event(std::string("property:")+key);change(1);}
static void zend_update_property_long(int,zval*,const char*key,size_t,long n){event(std::string("property-long:")+key+":"+std::to_string(n));state.property=n;change(7);}
static void zval_addref_p(zval*z){event("addref");++z->owner->refs;}
static void zval_delref_p(zval*z){event("delref");--z->owner->refs;}
static int swoole_get_last_error(){event("last-error");return last_error;}
static const char*swoole_strerror(int){event("strerror");return "native-error";}
static int swoole_client_async_ce;
static int zend_parse_parameters(int,const char*,char**p,size_t*n,zval**value){*p=event_name.data();*n=event_name.size();*value=&callback_value;return 0;}
static Client*php_swoole_client_async_new(zval*,char*,int,int){event("new-client");if(bits&512)return nullptr;auto*p=new Client;p->socket.stream=scenario%2==0;p->ssl_wait_handshake=bits&1024;return p;}
static zval*sw_zend_read_property(int,zval*,const char*,size_t,int){event("read-settings");change(2);return bits&2048?nullptr:&settings;}
static bool php_swoole_client_check_setting(Client*,zval*){event("apply-settings");change(8);return true;}
static Client*php_swoole_client_get_cli(zval*z){event("get-cli");return z->owner->cli;}
static void php_swoole_client_free(zval*z,Client*p){event("free-client");assert(live_clients.count(p));z->owner->cli=nullptr;delete p;}
static void client_onReceive(const Client*,const char*,size_t){event("receive-stub");}
static void client_onConnect(Client*);static void client_onClose(Client*);static void client_onError(Client*);static void client_onBufferFull(Client*);static void client_onBufferEmpty(Client*);
int Client::connect(const char*,int,double,int){event("connect");change(5);const int result=scenario%3==0?0:-1;errno=scenario%3==1?0:17;last_error=bits&4096?SW_ERROR_DNSLOOKUP_RESOLVE_FAILED:901;auto callback=onError;if(result<0&&(bits&8192)&&callback)callback(this);return result;}
// SLOT_HELPER
// ACTUAL_BODY
static std::string run(unsigned input,unsigned sc,unsigned mut,int failure,unsigned operation,std::string name="connect"){
 cleaning=true;state=ClientObject();for(unsigned n=0;n<4;++n)reserves.push_back(new zend::Callable(200+n));state.async=new AsyncClientObject();live_containers.insert(state.async);for(unsigned n=1;n<=7;++n)if(input&(1u<<(n-1)))*slot(&state,n)=new zend::Callable(n);settings.array=input&16;bits=input;scenario=sc;mutation=mut;fail_at=failure;event_count=0;callback_id=100;last_error=901;args.text=input&16384?std::string():"host";args.long_index=0;event_name=std::move(name);Return result;std::string exception;trace.str("");trace.clear();
 if(operation==4&&(input&32768)){state.cli=new Client;state.cli->object=&object;}
 if((operation==0||operation==4)&&(input&65536)){live_containers.erase(state.async);delete state.async;state.async=nullptr;}
 Client *connect_client=nullptr;if(operation==3){connect_client=new Client;connect_client->object=&object;connect_client->ssl_wait_handshake=input&1024;}
 errno=17;cleaning=false;
 try{switch(operation){case 0:method_on(&result);break;case 1:{unsigned types[]={1,3,4,5,6,7};client_execute_callback(&object,static_cast<AsyncClientCallbackType>(types[sc%6]));break;}case 2:php_swoole_client_async_free_object(&state);state.async=nullptr;break;case 3:client_onConnect(connect_client);break;case 4:method_connect(&result);break;}}catch(const std::exception&e){exception=e.what();}
 std::ostringstream answer;answer<<trace.str()<<"|throw="<<exception<<"|return="<<result.kind<<','<<result.value<<"|state="<<(state.cli!=nullptr)<<','<<(state.async!=nullptr)<<','<<(operation==2?0:mask())<<','<<state.refs<<','<<state.property<<','<<errno<<"|live="<<live_callbacks.size()<<','<<live_clients.size();
 if(state.cli){auto*p=state.cli;answer<<"|callbacks="<<(p->onConnect!=nullptr)<<(p->onClose!=nullptr)<<(p->onError!=nullptr)<<(p->onReceive!=nullptr)<<(p->onBufferFull!=nullptr)<<(p->onBufferEmpty!=nullptr);}
 if(connect_client&&live_clients.count(connect_client))answer<<"|sslwait="<<connect_client->ssl_wait_handshake;
 cleaning=true;while(!live_clients.empty())delete static_cast<Client*>(*live_clients.begin());while(!live_callbacks.empty())delete static_cast<zend::Callable*>(*live_callbacks.begin());while(!live_containers.empty())delete static_cast<AsyncClientObject*>(*live_containers.begin());reserves.clear();state.async=nullptr;state.cli=nullptr;return answer.str();
}
}
// DRIVER
