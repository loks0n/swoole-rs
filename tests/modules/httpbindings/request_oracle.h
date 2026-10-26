#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <array>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cctype>
#include <cstdint>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <strings.h>
#define SW_STRL(s) s, sizeof(s)-1
#define SW_STRCASEEQ(s,n,v) swoole_strcaseeq(s,n,SW_STRL(v))
#define SW_STR_ISTARTS_WITH(s,n,v) swoole_str_istarts_with(s,n,SW_STRL(v))
#define SW_ZSTR_KNOWN(s) s
#ifndef SWR_HTTPBINDINGS_NO_COMPRESSION
#define SW_HAVE_COMPRESSION 1
#endif
#define SW_LOG_TRACE 1
#define SW_ERROR_SESSION_CLOSED 2
#define SW_TRACE_HTTP 1
#define SW_ZEND_STR_COOKIE "cookie"
#define SW_ZEND_STR_HOST "host"
#define SW_ZEND_STR_USER_AGENT "user-agent"
#define SW_ZEND_STR_ACCEPT "accept"
#define SW_ZEND_STR_CONTENT_TYPE "content-type"
#define SW_ZEND_STR_CONTENT_LENGTH "content-length"
#define SW_ZEND_STR_AUTHORIZATION "authorization"
#define SW_ZEND_STR_CONNECTION "connection"
#define SW_ZEND_STR_ACCEPT_ENCODING "accept-encoding"
#define SW_ZEND_STR_QUERY_STRING "query_string"
#define SW_ZEND_STR_GET "get"
#define PARSE_STRING 1
#define SW_STACK_BUFFER_SIZE 65536
struct Exit {};
struct Oracle {
    std::vector<std::string> trace;
    std::set<char *> allocated;
    size_t fail=SIZE_MAX;
    std::function<void(const std::string&)> observe;
    ~Oracle(){for(auto*p:allocated)free(p);}
    void event(const std::string &s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(observe)observe(s);}
};
extern thread_local Oracle *oracle;
inline char *estrndup(const char *p,size_t n){oracle->event("dup:"+std::string(p,n));char*s=(char*)malloc(n+1);memcpy(s,p,n);s[n]=0;oracle->allocated.insert(s);return s;}
inline void efree(char*p){oracle->event("free:"+std::string(p));oracle->allocated.erase(p);free(p);}
struct zval {std::string text;std::map<std::string,std::vector<std::string>> hash;};
using HashTable=zval;
#define Z_ARR_P(p) (p)
inline void ZVAL_STRINGL(zval*z,char*p,size_t n){oracle->event("zval:"+std::string(p,n));z->text.assign(p,n);}
inline void zend_hash_update(zval*z,const char*key,zval*value){oracle->event("hash:"+std::string(key)+":"+value->text);z->hash[key]={value->text};}
inline void zend_str_tolower_copy(char*out,const char*in,size_t n){oracle->event("lower:"+std::string(in,n));for(size_t i=0;i<n;i++)out[i]=in[i]>='A'&&in[i]<='Z'?in[i]+32:in[i];out[n]=0;}
namespace zend {inline void array_add_or_merge(zval*z,char*key,size_t n,zval*value){std::string k(key,n);oracle->event("merge:"+k+":"+value->text);z->hash[k].push_back(value->text);}}
inline zval *swoole_http_init_and_read_property(int,zval*,zval**slot,const char*key){oracle->event("property:"+std::string(key));return *slot;}
inline void swoole_http_parse_cookie(zval*z,const char*p,size_t n){oracle->event("cookie:"+std::string(p,n));z->text.append(p,n);}
inline void http_server_add_server_array(zval*z,const char*key,zval*v){oracle->event("server:"+std::string(key)+":"+v->text);z->hash[key]={v->text};}
inline void swoole_php_treat_data(int,char*p,zval*z){oracle->event("treat:"+std::string(p));z->text=p;oracle->allocated.erase(p);free(p);}
inline void log_format(const char*kind,const char*fmt,va_list args){char s[512];vsnprintf(s,sizeof(s),fmt,args);oracle->event(std::string(kind)+s);}
inline void swoole_error_log(int,int,const char*fmt,...){va_list args;va_start(args,fmt);log_format("error:",fmt,args);va_end(args);}
inline void swoole_trace_log(int,const char*fmt,...){va_list args;va_start(args,fmt);log_format("trace:",fmt,args);va_end(args);}
inline char *php_strtok_r(char*p,const char*d,char**save){return strtok_r(p,d,save);}
struct Scratch {char str[4096];size_t size=sizeof(str);};
extern thread_local Scratch scratch;
inline Scratch *sw_tg_buffer(){return &scratch;}
namespace swoole {namespace websocket {static constexpr int STATUS_CONNECTION=1;} }
struct Connection {int server_fd=9,websocket_status=0;};
struct ListenPort {bool open_websocket_protocol=false;};
struct Server {
    Connection conn;ListenPort port;bool found=true;
    Connection *get_connection_by_session_id(long fd){oracle->event("connection:"+std::to_string(fd));return found?&conn:nullptr;}
    ListenPort *get_port_by_server_fd(int fd){oracle->event("port:"+std::to_string(fd));return &port;}
};
struct HttpContext {
    struct Request {
        zval header,cookie,server,get,object;
        zval*zheader=&header,*zcookie=&cookie,*zserver=&server,*zget=&get,*zobject=&object;
        bool post_form_urlencoded=false;char*path=nullptr;size_t path_len=0;
    } request;
    const char*current_header_name=nullptr;size_t current_header_name_len=0,current_header_value_len=0;
    bool parse_cookie=false,enable_compression=false,websocket=false,recv_chunked=false,co=false,boundary=true;
    int compression=0,initializations=0;long fd=42;Server server;
    bool is_co_socket(){oracle->event("is-co");return co;}
    Server *get_async_server(){oracle->event("server");return &server;}
    bool get_multipart_boundary(const char*p,size_t n,size_t offset,char**out,int*length){oracle->event("boundary:"+std::to_string(offset)+":"+std::string(p,n));*out=(char*)"fake-boundary";*length=13;return boundary;}
    bool init_multipart_parser(char*p,int n){oracle->event("init:"+std::string(p,n));initializations++;return false;}
    void set_compression_method(const char*p,size_t n){oracle->event("compression:"+std::string(p,n));compression++;}
};
struct llhttp_t {void*data=nullptr;uint32_t method=0;};
static constexpr int HTTP_DELETE=0,HTTP_POST=3,HTTP_PUT=4,HTTP_PATCH=28,HTTP_QUERY=46,HPE_USER=24;
inline void llhttp_set_error_reason(llhttp_t*,const char*reason){oracle->event("error-reason:"+std::string(reason));}
static constexpr int swoole_http_request_ce=0;
#define REQUEST_DECL(namespace_name) namespace namespace_name { \
int call_header(llhttp_t*,const char*,size_t);int call_url(llhttp_t*,const char*,size_t); \
int swoole_http_token_list_contains_value(const char*,size_t,const char*); \
char *call_trim(char*,size_t*);void call_key(char*,int); }
REQUEST_DECL(upstream_request)
REQUEST_DECL(candidate_request)
