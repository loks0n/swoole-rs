/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#define PHP_METHOD(c,n) void method_##n(Return *return_value)
#define sw_inline inline
#define ZEND_THIS (&object)
#define SW_Z8_OBJ_P(z) (z)
#define SW_ZSTR_KNOWN(z) 0
#define ZEND_STRL(s) s,sizeof(s)-1
#define ZEND_NUM_ARGS() 3
#define FAILURE -1
#define ZEND_PARSE_PARAMETERS_START(a,b) do {
#define ZEND_PARSE_PARAMETERS_END_EX(e) } while(0)
#define Z_PARAM_OPTIONAL
#define Z_PARAM_STRING(p,n) p=args.text.data();n=args.text.size();
#define Z_PARAM_LONG(p) p=args.long_index++==0?args.port:args.flags;
#define Z_PARAM_DOUBLE(p) p=args.timeout;
#define ZSTR_VAL(s) ((s)->bytes.data())
#define ZSTR_LEN(s) ((s)->length)
#define ZVAL_IS_ARRAY(z) ((z)->array)
#define RETVAL_FALSE do{return_value->kind=1;return_value->number=0;}while(0)
#define RETVAL_TRUE do{return_value->kind=1;return_value->number=1;}while(0)
#define RETURN_FALSE do{RETVAL_FALSE;return;}while(0)
#define RETURN_TRUE do{RETVAL_TRUE;return;}while(0)
#define RETURN_LONG(n) do{return_value->kind=2;return_value->number=(n);return;}while(0)
#define RETURN_EMPTY_STRING() do{return_value->kind=3;return_value->bytes.clear();return;}while(0)
#define RETURN_STR(s) do{return_value->kind=3;return_value->bytes.assign(ZSTR_VAL(s),ZSTR_LEN(s));return;}while(0)
#define CLIENT_CORO_GET_SOCKET_SAFE(name) SocketImpl*name=get_safe_socket();if(!name){php_swoole_socket_set_error_properties(ZEND_THIS,999,"not connected");RETURN_FALSE;}
// DECLARATIONS
namespace BODY_NAMESPACE {
using zend_long=long;constexpr int E_WARNING=2,SW_SOCK_TCP=1,SW_SOCK_UDP=2,SW_SOCK_TCP6=3,SW_SOCK_UNIX_STREAM=5,SW_TIMEOUT_CONNECT=1,SW_TIMEOUT_RDWR=2,SW_TIMEOUT_WRITE=3,SW_TIMEOUT_READ=4,SW_PHP_CLIENT_BUFFER_SIZE=1024;
struct zval{long number=1;bool array=true;};static zval object,type_value,settings;
struct Return{int kind=0;long number=0;std::string bytes;};
struct Args{std::string text;long port=80,flags=0;double timeout=1.5;unsigned long_index=0;}static args;
struct zend_string{size_t length;std::array<char,512>bytes;};static std::vector<zend_string*>strings;
struct SocketImpl;struct ClientCoroObject{SocketImpl*socket=nullptr;}static client;
static unsigned bits,scenario,mutation;static int fail_at,event_count,coercions;static std::ostringstream trace;
static void event(const std::string&,bool throwing=true);static void change(unsigned);
static zend_string*zend_string_alloc(size_t n,bool){event("string-alloc:"+std::to_string(n));auto*p=new zend_string;p->length=n;p->bytes.fill('z');strings.push_back(p);return p;}
static void zend_string_free(zend_string*p){event("string-free");for(auto &item:strings)if(item==p){delete p;item=nullptr;return;}assert(false);}
struct SocketImpl {
 int id=0,errCode=0,type=1;bool open_length_check=false,open_eof_check=false;zend_string*packet=nullptr;
 void set_timeout(double n,int t){event("timeout:"+std::to_string(id)+":"+std::to_string(t)+":"+std::to_string(n));change(4);}
 bool connect(const char*host,int port,int flags){event("connect:"+std::to_string(id)+":"+std::string(host)+":"+std::to_string(port)+":"+std::to_string(flags));change(5);return !(bits&32);}
 bool close(){event("close:"+std::to_string(id));client.socket=nullptr;return true;}
 ssize_t send_all(const char*p,size_t n){event("send:"+std::to_string(id)+":"+std::string(p,n));change(6);switch(scenario%5){case 0:return -1;case 1:return 0;case 2:return static_cast<ssize_t>(n)-1;case 3:return n;default:return n+1;}}
 ssize_t recv_packet(double){event("recv-packet:"+std::to_string(id));change(7);ssize_t n=scenario%4==0?-1:scenario%4==1?0:scenario%4==2?3:7;if(n>0){packet=zend_string_alloc(n,false);std::memcpy(packet->bytes.data(),"pa\0cket",7);}return n;}
 char*pop_packet(){event("pop-packet:"+std::to_string(id));return bits&64?nullptr:packet->bytes.data();}
 void set_err(int n){event("set-error:"+std::to_string(n));errCode=n;}
 ssize_t recv(char*p,size_t capacity){event("recv:"+std::to_string(id)+":"+std::to_string(capacity));change(7);ssize_t n=scenario%4==0?-1:scenario%4==1?0:scenario%4==2?3:7;if(n>0){assert(static_cast<size_t>(n)<=capacity);std::memcpy(p,"ra\0data",n);}return n;}
 int get_type(){event("get-type:"+std::to_string(id));return type;}
 bool sendfile(const char*file,off_t offset,size_t length){event("sendfile:"+std::string(file)+":"+std::to_string(offset)+":"+std::to_string(length));change(8);return !(bits&128);}
 struct TimeoutSetter{SocketImpl*s;TimeoutSetter(SocketImpl*p,double n,int type):s(p){event("ts-create:"+std::to_string(s->id)+":"+std::to_string(type)+":"+std::to_string(n));change(9);}~TimeoutSetter(){event("ts-dtor:"+std::to_string(s->id),false);s->errCode=(bits&256)?99:s->errCode;}};
};
static SocketImpl sockets[3];static int swoole_client_coro_ce;
static void event(const std::string&name,bool throwing){trace<<name<<':'<<(client.socket?client.socket->id:-1)<<','<<type_value.number<<','<<settings.array<<';';if(event_count++==fail_at&&throwing)throw std::runtime_error(name);}
static void change(unsigned point){if(mutation!=point)return;settings.array=!settings.array;type_value.number=type_value.number==1?2:1;if(point==3)client.socket=&sockets[2];if(point==6||point==7)sockets[0].errCode=77;}
static ClientCoroObject*client_coro_get_client(const zval*){event("get-client");return &client;}
static SocketImpl*get_safe_socket(){event("get-safe");return bits&512?nullptr:client.socket;}
static zval*sw_zend_read_property(int,zval*,const char*,size_t,int){event("read-type");change(1);return &type_value;}
static zval*sw_zend_read_property_ex(int,zval*,int,int){event("read-setting");change(2);return bits&16?nullptr:&settings;}
static long zval_get_long(zval*z){event("get-long");if(coercions++==0)change(10);return z->number;}
static int php_swoole_client_get_type(long n){event("client-type:"+std::to_string(n));return n&255;}
struct NetSocket{static bool is_tcp(int t){event("is-tcp:"+std::to_string(t));return t==SW_SOCK_TCP||t==SW_SOCK_TCP6;}};
struct Address{static bool verify_port(int port,bool){event("verify-port:"+std::to_string(port));return port>0&&port<=65535;}};
static SocketImpl*client_coro_create_socket(zval*,long n){event("create:"+std::to_string(n));change(3);return bits&8?nullptr:&sockets[1];}
static bool php_swoole_socket_set(SocketImpl*s,zval*){event("apply:"+std::to_string(s->id));change(11);return bits&1024;}
static void php_swoole_socket_set_error_properties(zval*,SocketImpl*s){event("error-socket:"+std::to_string(s->id)+":"+std::to_string(s->errCode));change(12);}
static void php_swoole_socket_set_error_properties(zval*,int n,const char*message=""){event("error-code:"+std::to_string(n)+":"+message);}
static void php_swoole_fatal_error(int,const char*message){event(std::string("warning:")+message);}
static void zend_update_property_bool(int,zval*,const char*,size_t,int n){event("connected:"+std::to_string(n));}
static void zend_update_property_long(int,zval*,const char*,size_t,long n){event("property-long:"+std::to_string(n));}
static void zend_update_property_string(int,zval*,const char*,size_t,const char*p){event(std::string("property-string:")+p);}
static int zend_parse_parameters(int,const char*,char**p,size_t*n,long*offset,long*length){*p=args.text.data();*n=args.text.size();*offset=args.port;*length=args.flags;return 0;}
namespace zend{static zend_string*fetch_zend_string_by_val(char*p){event("fetch-packet");for(auto*s:strings)if(s&&s->bytes.data()==p)return s;assert(false);return nullptr;}}
// ACTUAL_BODY
static std::string run(unsigned input,unsigned sc,unsigned mut,int failure,unsigned operation){
 bits=input;scenario=sc;mutation=mut;fail_at=failure;event_count=coercions=0;trace.str("");trace.clear();strings.clear();
 int types[]={SW_SOCK_TCP,SW_SOCK_UDP,SW_SOCK_TCP6,SW_SOCK_UNIX_STREAM,6,999,SW_SOCK_TCP};int ports[]={-1,0,1,80,65535,65536,99999};
 for(int i=0;i<3;++i){sockets[i]=SocketImpl();sockets[i].id=i;sockets[i].type=types[sc%7];sockets[i].errCode=bits&4?5:0;sockets[i].open_length_check=bits&2;sockets[i].open_eof_check=bits&4;}
 client.socket=bits&1?&sockets[0]:nullptr;type_value.number=types[sc%7];settings.array=bits&4;args.text=bits&2?std::string():std::string("a\0data",6);args.port=ports[sc%7];args.flags=bits&4?-1:9;args.timeout=1.5;args.long_index=0;Return result;std::string exception;int helper=-2;
 try{switch(operation){case 0:{auto*p=client_coro_get_socket_for_connect(&object,args.port);helper=p?p->id:-1;break;}case 1:method_connect(&result);break;case 2:method_send(&result);break;case 3:method_recv(&result);break;case 4:method_sendfile(&result);break;}}catch(const std::exception&e){exception=e.what();}
 std::ostringstream answer;answer<<trace.str()<<"|throw="<<exception<<"|helper="<<helper<<"|return="<<result.kind<<','<<result.number<<',';for(unsigned char c:result.bytes)answer<<std::hex<<unsigned(c)<<'.';answer<<"|state="<<(client.socket?client.socket->id:-1)<<','<<type_value.number<<','<<settings.array<<','<<coercions;size_t live=0;for(auto*s:strings)if(s){++live;delete s;}answer<<"|live="<<live;return answer.str();
}
}
// DRIVER
