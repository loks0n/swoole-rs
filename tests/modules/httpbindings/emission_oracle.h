#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#ifndef EMISSION_NO_COMPRESSION
#define SW_HAVE_COMPRESSION 1
#endif
#ifndef EMISSION_NO_ZLIB
#define SW_HAVE_ZLIB 1
#endif
#define ZEND_STRL(s) s,sizeof(s)-1
#define IS_STRING 2
#define E_WARNING 2
#define SW_ERROR_NO_PAYLOAD 1
#define SW_WEBSOCKET_EXTENSION_DEFLATE "permessage-deflate; server_no_context_takeover; client_no_context_takeover"
struct Exit {};
struct Oracle {
 std::vector<std::string> trace;std::vector<void*>allocated;size_t fail=SIZE_MAX;unsigned failed_send=0,sends=0;std::function<void(const std::string&)>hook;
 ~Oracle(){for(auto p:allocated)free(p);}
 void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(hook)hook(s);}
};
extern thread_local Oracle*oracle;
struct zend_string {std::string value;char*val=nullptr;size_t len=0;};
struct zval {int type=IS_STRING;std::string value;};
#define ZSTR_VAL(p) ((p)->value.data())
#define ZSTR_LEN(p) ((p)->value.size())
#define ZVAL_IS_FALSE(p) ((p)->type==0)
#define Z_TYPE_P(p) ((p)->type)
#define Z_STRVAL_P(p) ((p)->value.data())
#define Z_STRLEN_P(p) ((p)->value.size())
#define Z_ARRVAL_P(p) (p)
#define RETURN_BOOL(v) do {return_value->type=(v)?1:0;return;}while(0)
#define RETURN_FALSE RETURN_BOOL(false)
#define RETURN_TRUE RETURN_BOOL(true)
struct String {
 std::string value;char*str=nullptr;size_t length=0;
 void update(){str=value.empty()?nullptr:&value[0];length=value.size();}
 void clear(){oracle->event("clear");value.clear();update();}
 void append(const char*p,size_t n){oracle->event("append:"+std::string(p?p:"",n));value.append(p?p:"",n);update();}
};
inline char*swoole_dec2hex(size_t n,unsigned){oracle->event("hex:"+std::to_string(n));char b[32];snprintf(b,sizeof b,"%zx",n);auto*p=strdup(b);oracle->allocated.push_back(p);return p;}
inline void sw_free(void*p){oracle->event("free-hex");oracle->allocated.erase(std::remove(oracle->allocated.begin(),oracle->allocated.end(),p),oracle->allocated.end());free(p);}
inline void php_swoole_error_ex(int,int,const char*s){oracle->event(std::string("warning:")+s);}
inline zval*zend_hash_str_find(zval*p,const char*,size_t){oracle->event("extension");return p&&p->type>=0?p:nullptr;}
namespace websocket {enum {STATUS_HANDSHAKE=1,STATUS_ACTIVE=2,STATUS_HANDSHAKE_FAILED=3};}
struct Connection {int websocket_status=websocket::STATUS_HANDSHAKE;bool websocket_compression=false;};
struct Server {
 bool present=true,websocket_compression=false;Connection connection;
 Connection*get_connection_verify(int){oracle->event("connection");return present?&connection:nullptr;}
};
struct Result {
 std::vector<std::string> trace;unsigned flags=0;int status=0,returned=-1;bool exited=false;std::string buffer;
 bool operator==(const Result&r)const{return trace==r.trace&&flags==r.flags&&status==r.status&&returned==r.returned&&exited==r.exited&&buffer==r.buffer;}
};
namespace upstream_emission {Result run(unsigned,size_t,bool,bool,unsigned,unsigned,size_t);}
namespace candidate_emission {Result run(unsigned,size_t,bool,bool,unsigned,unsigned,size_t);}
