#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <cassert>
#include <clocale>
#include <cstdint>
#include <cstring>
#include <strings.h>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#define SW_STRL(s) s, sizeof(s)-1
#define ZEND_STRL(s) SW_STRL(s)
#define SW_STRCASEEQ(s,n,v) swoole_strcaseeq(s,n,SW_STRL(v))
#define SW_ZSTR_KNOWN(s) s
#define SW_ZEND_STR_POST "post"
#define SW_BUFFER_SIZE_STD 8192
#define PARSE_STRING 1
#define SW_TRACE_HTTP 1
#define HPE_PAUSED 21
#ifndef PAYLOAD_CAPABILITIES
#define PAYLOAD_CAPABILITIES 7
#endif
#if PAYLOAD_CAPABILITIES
#define SW_HAVE_COMPRESSION 1
#endif
#if PAYLOAD_CAPABILITIES & 1
#define SW_HAVE_ZLIB 1
#endif
#if PAYLOAD_CAPABILITIES & 2
#define SW_HAVE_BROTLI 1
#endif
#if PAYLOAD_CAPABILITIES & 4
#define SW_HAVE_ZSTD 1
#endif
enum swHttpCompressMethod {HTTP_COMPRESS_NONE,HTTP_COMPRESS_GZIP,HTTP_COMPRESS_DEFLATE,HTTP_COMPRESS_BR,HTTP_COMPRESS_ZSTD};
struct Exit {};
struct Oracle {
 std::vector<std::string> trace;size_t fail=SIZE_MAX;std::set<char*>allocated;
 std::function<void(const std::string&)>hook;
 void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(hook)hook(s);}
 ~Oracle(){for(char*p:allocated)free(p);}
};
extern thread_local Oracle *oracle;
struct NativeString {
 std::string storage;const char*str=nullptr;size_t length=0;
 explicit NativeString(size_t){oracle->event("new-string");sync();}
 void sync(){str=storage.data();length=storage.size();}
 void append(const char*p,size_t n){oracle->event("append:"+std::string(p,n));storage.append(p,n);sync();}
};
namespace swoole {using String=NativeString;}
struct zval {std::string text;bool truth=false;long number=0;};
inline char *estrndup(const char*p,size_t n){oracle->event("duplicate:"+std::string(p,n));char*q=(char*)malloc(n+1);memcpy(q,p,n);q[n]=0;oracle->allocated.insert(q);return q;}
inline bool zval_is_true(zval*z){oracle->event("truth:"+z->text);return z->truth;}
inline long zval_get_long(zval*z){oracle->event("long:"+z->text);return z->number;}
namespace zend {struct String {zval*z;explicit String(zval*p):z(p){oracle->event("convert:"+z->text);}std::string to_std_string(){oracle->event("copy:"+z->text);return z->text;}};}
inline zval*swoole_http_init_and_read_property(int,zval*,zval**slot,const char*key){oracle->event("property:"+std::string(key));return *slot;}
inline void swoole_php_treat_data(int,char*p,zval*z){oracle->event("treat:"+std::string(p));z->text=p;oracle->allocated.erase(p);free(p);}
inline void multipart_parser_free(void*){oracle->event("multipart-free");}
inline void swoole_trace_log(int,const char*,size_t n){oracle->event("log:"+std::to_string(n));}
static constexpr int swoole_http_request_ce=0;
struct ContextData {
 struct Request {
  NativeString*chunked_body=nullptr;NativeString*h2_data_buffer=nullptr;
  const char*body_at=nullptr;size_t body_length=0;bool post_form_urlencoded=false;
  zval object,post;zval*zobject=&object,*zpost=&post;
 } request;
 bool recv_chunked=false,parse_body=false,parse_cookie=false,parse_files=false,enable_compression=false,websocket_compression=false;
 bool completed=false;long compression_level=0;void*mt_parser=nullptr;NativeString*form_data_buffer=nullptr;
 int accept_compression=0,compression_method=77;bool parse_result=true;
 std::string upload_tmp_dir;
 bool parse_multipart_data(const char*p,size_t n){oracle->event("multipart:"+std::string(p,n));return parse_result;}
 ~ContextData(){delete request.chunked_body;delete request.h2_data_buffer;delete form_data_buffer;}
};
struct llhttp_t {void*data=nullptr;};
struct Input {uint32_t flags;std::string bytes,prior;size_t previous=0;bool parse_result=true;};
struct Result {
 std::vector<std::string>trace;std::string body,post,directory,encoding;long offset=-999;size_t length=0;int code=0,accepted=0,method=0;
 uint32_t flags=0;long level=0;bool exited=false;
 bool operator==(const Result&r)const{return trace==r.trace&&body==r.body&&post==r.post&&directory==r.directory&&encoding==r.encoding&&offset==r.offset&&length==r.length&&code==r.code&&accepted==r.accepted&&method==r.method&&flags==r.flags&&level==r.level&&exited==r.exited;}
};
#define PAYLOAD_DECL(N) namespace N {Result body(const Input&,size_t);Result complete(const Input&,size_t);Result option(const std::string&,zval,size_t,bool);Result compression(const std::string&,size_t,int);}
PAYLOAD_DECL(upstream_payload)
PAYLOAD_DECL(candidate_payload)
