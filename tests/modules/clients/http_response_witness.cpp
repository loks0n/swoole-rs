/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#define sw_unlikely(x) (x)
#define sw_likely(x) (x)
#define ZEND_STRL(s) s,sizeof(s)-1
#define swoole_trace_log(tag,fmt,...) trace_call(__VA_ARGS__)
// DECLARATIONS
namespace BODY_NAMESPACE {
constexpr int HTTP_RESPONSE=1,HPE_OK=0,SW_TIMEOUT_READ=1,SW_ERROR_HTTP_INVALID_PROTOCOL=700,SW_LOG_TRACE=1,SW_WEBSOCKET_HEADER_LEN=2,HTTP_ESTATUS_REQUEST_TIMEOUT=-2,HTTP_ESTATUS_SERVER_RESET=-3;
struct Client;static Client *active;static unsigned bits,scenario,mutation;static int fail_at,event_count;static unsigned receive_count,parse_count,ticks;
static std::ostringstream trace;static void event(const std::string&,bool throwing=true);static void change(unsigned);
struct String {
 std::array<char,64> storage{};char *str=storage.data();size_t size=32,length=0,offset=0;
 void clear(){event("buffer-clear");length=0;}
 void reduce(size_t n){event("buffer-reduce:"+std::to_string(n));assert(n<=length);std::memmove(str,str+n,length-n);length-=n;offset=0;}
};
struct Parser {void *data=nullptr;int error=0,upgrade=0;};
namespace websocket {static int get_package_length(){return 0;}}
struct Protocol {int package_length_size=0,package_length_offset=9,package_body_offset=8;int(*get_package_length)()=nullptr;};
struct Socket {
 static constexpr double default_read_timeout=7.5;String buffer;int errCode=0,close_wait=0,id=0;bool open_length_check=false;Protocol protocol;
 String *get_read_buffer(){event("get-buffer:"+std::to_string(id));return &buffer;}
 Socket *get_socket(){event("get-socket:"+std::to_string(id));return this;}
 void set_err(int code){event("set-error:"+std::to_string(code));errCode=code;}
 ssize_t recv(char *dest,size_t capacity);
 struct TimeoutController {Socket *socket;explicit TimeoutController(Socket*s,double timeout,int):socket(s){event("tc-create:"+std::to_string(timeout));change(2);}~TimeoutController(){event("tc-dtor:"+std::to_string(socket->id),false);}bool has_timedout(int){event("timeout");return (scenario==6&&ticks++==0)||(scenario==7&&ticks++==1);}};
};
namespace network {using Socket=BODY_NAMESPACE::Socket;}
static Socket sockets[2];static int http_parser_settings=0;
struct Client {
 Socket *socket=&sockets[0];Parser parser;bool wait_response=true,completed=false,event_stream=false,websocket=false,keep_alive=true,connection_close=false;double response_timeout=0;int property_error=0,status=0;void *zobject=this;
 bool recv_response(double timeout);
 bool close(){event("close");change(8);socket=nullptr;return true;}
 void reset(){event("reset");change(9);wait_response=false;completed=false;event_stream=false;}
};
static void event(const std::string &name,bool throwing){trace<<name<<':'<<(active->socket?active->socket->id:-1)<<','<<active->wait_response<<active->completed<<active->event_stream<<active->websocket<<active->keep_alive<<active->connection_close<<';';if(event_count++==fail_at&&throwing)throw std::runtime_error(name);}
static void change(unsigned point){if(mutation!=point)return;active->event_stream=!active->event_stream;active->websocket=!active->websocket;active->keep_alive=!active->keep_alive;active->connection_close=!active->connection_close;active->response_timeout=2.25;if(point==2)active->socket=&sockets[1];if(point==5)active->socket->close_wait=!active->socket->close_wait;if(point==7)active->socket->errCode=ETIMEDOUT;}
ssize_t Socket::recv(char *dest,size_t capacity){
 event("recv:"+std::to_string(id)+":"+std::to_string(capacity));change(3);unsigned call=receive_count++;
 if(scenario==0)return -1;if(scenario==1)return 0;
 std::string chunk;
 if(scenario==2)chunk=call==0?"HEADER":call==1?"\r\n\r\nA":"";
 else if(scenario==3)chunk=call==0?std::string(32,'x'):"";
 else if(scenario==4)chunk=call==0?"H\r\n\r\nA":"";
 else if(scenario==5)chunk=call==0?"H\r\n\r\nA":call==1?"more":"";
 else chunk=call==0?"H\r\n\r\nA":"";
 assert(chunk.size()<=capacity);std::memcpy(dest,chunk.data(),chunk.size());return chunk.size();
}
static void swoole_llhttp_parser_init(Parser*p,int,void*data){event("parser-init");p->data=data;p->error=0;p->upgrade=0;change(1);}
static bool llhttp_should_keep_alive(Parser*){event("should-keepalive");return bits&2;}
static bool llhttp_message_needs_eof(Parser*){event("needs-eof");return bits&8;}
static int llhttp_finish(Parser*){event("parser-finish");change(6);return 0;}
static ssize_t swoole_strnpos(const char*p,size_t n,const char*s,size_t m){event("find-header:"+std::to_string(n));change(4);auto found=std::string(p,n).find(std::string(s,m));return found==std::string::npos?-1:static_cast<ssize_t>(found);}
static size_t swoole_llhttp_parser_execute(Parser*p,int*,const char*data,size_t n){
 event("parse:"+std::to_string(n)+":"+std::string(data,n));change(5);p->error=(bits&16)?17:0;p->upgrade=(bits&256)?1:0;active->socket->close_wait=(bits&512)?1:active->socket->close_wait;active->completed=(bits&1024)||parse_count>0;parse_count++;return bits&2048?n/2:n;
}
static void trace_call(size_t parsed,ssize_t received,size_t total,bool complete){event("trace:"+std::to_string(parsed)+":"+std::to_string(received)+":"+std::to_string(total)+":"+std::to_string(complete));}
static void swoole_error_log(int,int,const char*){event("header-too-large");}
static void php_swoole_socket_set_error_properties(void*,Socket*s){event("error-properties:"+std::to_string(s->id));active->property_error=s->errCode;change(7);}
namespace zend {static void object_set(void*,const char*,size_t,int n){event("status:"+std::to_string(n));active->status=n;}}
// ACTUAL_BODY
static std::string run(unsigned input,unsigned sc,unsigned mut,int failure){
 bits=input;scenario=sc;mutation=mut;receive_count=parse_count=ticks=0;fail_at=failure;event_count=0;trace.str("");trace.clear();
 for(int i=0;i<2;++i){sockets[i].buffer.storage.fill(0);sockets[i].buffer.length=sockets[i].buffer.offset=0;sockets[i].buffer.size=32;sockets[i].id=i;sockets[i].errCode=sockets[i].close_wait=0;sockets[i].open_length_check=false;sockets[i].protocol=Protocol();}
 Client cli;active=&cli;cli.wait_response=bits&1;cli.event_stream=bits&4;cli.websocket=bits&32;cli.keep_alive=bits&64;cli.connection_close=bits&128;cli.response_timeout=bits&4096?1.25:0;bool result=false;std::string exception;
 try{result=cli.recv_response(bits&8192?3.0:0.0);}catch(const std::exception&e){exception=e.what();}
 std::ostringstream answer;answer<<trace.str()<<"|result="<<result<<"|throw="<<exception<<"|state="<<(cli.socket?cli.socket->id:-1)<<','<<cli.wait_response<<cli.completed<<cli.event_stream<<cli.websocket<<cli.keep_alive<<cli.connection_close<<','<<cli.property_error<<','<<cli.status<<','<<receive_count<<','<<parse_count;
 for(auto&s:sockets){answer<<"|socket="<<s.id<<','<<s.errCode<<','<<s.close_wait<<','<<s.open_length_check<<','<<s.protocol.package_length_size<<','<<s.protocol.package_length_offset<<','<<s.protocol.package_body_offset<<','<<(s.protocol.get_package_length!=nullptr)<<','<<s.buffer.length<<','<<s.buffer.offset<<',';for(unsigned char c:s.buffer.storage)answer<<std::hex<<unsigned(c)<<'.';}
 active=nullptr;return answer.str();
}
}
// DRIVER
