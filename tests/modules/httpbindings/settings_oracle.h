#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <climits>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>
#ifndef SETTINGS_NO_COMPRESSION
#define SW_HAVE_COMPRESSION 1
#endif
#define E_ERROR 1
struct Exit{};
struct zval {int kind=0;bool truth=false;int64_t number=0;std::string text;std::vector<zval>array;};
using zend_long=int64_t;
using HashTable=std::map<std::string,zval>;
struct Oracle {
 std::vector<std::string>trace;size_t fail=SIZE_MAX;bool completed=false,returned_false=false,dir_ok=true;
 std::set<char*>allocated;HashTable*table=nullptr;std::function<void(const std::string&)>hook;
 void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(hook)hook(s);}
 ~Oracle(){for(auto*p:allocated)free(p);}
};
extern thread_local Oracle*oracle;
#define ZVAL_IS_NULL(z) ((z)->kind==0)
#define ZVAL_IS_ARRAY(z) ((z)->kind==4)
#define Z_ARRVAL_P(z) (z)
#define RETURN_FALSE do{oracle->returned_false=true;return;}while(0)
inline zval*zend_hash_str_find(HashTable*table,const char*key,size_t n){std::string name(key,n);oracle->event("lookup:"+name);auto i=table->find(name);return i==table->end()?nullptr:&i->second;}
#define php_swoole_array_get_value(ht,key,value) ((value=zend_hash_str_find(ht,key,sizeof(key)-1))&&!ZVAL_IS_NULL(value))
inline bool zval_is_true(zval*z){oracle->event("truth:"+z->text);return z->truth;}
inline zend_long zval_get_long(zval*z){oracle->event("long:"+z->text);return z->number;}
inline void sw_free(void*p){oracle->event("free");oracle->allocated.erase(static_cast<char*>(p));free(p);}
namespace zend {struct String {
 std::string value;
 explicit String(zval*z){oracle->event("string:"+z->text);value=z->text;}
 const char*val()const{return value.data();}size_t len()const{return value.size();}
 std::string to_std_string()const{oracle->event("copy:"+value);return value;}
 char*dup()const{oracle->event("dup:"+value);if(value.empty())return nullptr;char*p=strndup(value.data(),value.size());oracle->allocated.insert(p);return p;}
};}
#define SW_HASHTABLE_FOREACH_START(z,v) for(auto&_item:(z)->array){v=&_item;
#define SW_HASHTABLE_FOREACH_END() }
inline void php_swoole_fatal_error(int,const char*format,...){char s[512];va_list args;va_start(args,format);vsnprintf(s,sizeof(s),format,args);va_end(args);oracle->event("fatal:"+std::string(s));}
inline int php_swoole_create_dir(const char*p,size_t n){oracle->event("directory:"+std::string(p,n));return oracle->dir_ok?0:-1;}
namespace WebSocket {inline void apply_setting(int&state,HashTable*,bool enabled){oracle->event("websocket");state=enabled?17:19;}}
namespace std {template<class T>shared_ptr<T>settings_make_shared(){oracle->event("new-types");return std::make_shared<T>();}}
#define make_shared settings_make_shared
struct HttpServer {
 bool parse_cookie=true,parse_post=true,parse_files=false,compression=true;uint8_t compression_level=1;uint32_t compression_min_length=128;
 int websocket_settings=0;std::shared_ptr<std::unordered_set<std::string>>compression_types;char*upload_tmp_dir=nullptr;
};
struct Input {HashTable table;bool dir_ok=true;unsigned hook=0;};
struct Result {
 std::vector<std::string>trace;std::set<std::string>types;std::string upload;
 uint32_t flags=0,minimum=0,level=0;int websocket=0;bool replaced=false,exited=false,completed=false,returned_false=false;
 bool operator==(const Result&r)const{return trace==r.trace&&types==r.types&&upload==r.upload&&flags==r.flags&&minimum==r.minimum&&level==r.level&&websocket==r.websocket&&replaced==r.replaced&&exited==r.exited&&completed==r.completed&&returned_false==r.returned_false;}
};
#define SETTINGS_DECL(N) namespace N {Result run(const Input&,size_t);}
SETTINGS_DECL(upstream_settings)
SETTINGS_DECL(candidate_settings)
