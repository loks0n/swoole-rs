#pragma once
#include "emission_oracle.h"
#include <cstdarg>
#include <cstdint>
#include <cinttypes>
#include <sys/types.h>
using zend_long=int64_t;
#define ZEND_LONG_FMT "%" PRId64
inline void php_swoole_error(int,const char*format,...){char b[256];va_list args;va_start(args,format);vsnprintf(b,sizeof b,format,args);va_end(args);oracle->event(std::string("warning:")+b);}
struct FileName{const char*data;size_t length;};
namespace swoole{namespace mime_type{inline std::string get(FileName name){oracle->event("mime:"+std::string(name.data,name.length));return "application/bin";}}}
inline zval*sw_zend_read_and_convert_property_array(int,void*object,const char*,size_t,int){oracle->event("headers");return static_cast<zval*>(object);}
inline bool zend_hash_str_exists(zval*p,const char*,size_t){oracle->event("mime-exists");return p->type!=0;}
inline void add_assoc_stringl(zval*p,const char*,const char*v,size_t n){oracle->event("add-mime:"+std::string(v,n));p->type=1;p->value.assign(v,n);}
static constexpr int swoole_http_response_ce=1;
struct FileResult{std::vector<std::string>trace;unsigned flags=0;bool returned=false,exited=false;std::string mime;
 bool operator==(const FileResult&r)const{return trace==r.trace&&flags==r.flags&&returned==r.returned&&exited==r.exited&&mime==r.mime;}};
struct RangeResult{std::vector<std::string>trace;int64_t length=0;int returned=-1;bool operator==(const RangeResult&r)const{return trace==r.trace&&length==r.length&&returned==r.returned;}};
namespace upstream_file{FileResult run(unsigned,size_t,unsigned,size_t);RangeResult range(int64_t,int64_t,int64_t);}
namespace candidate_file{FileResult run(unsigned,size_t,unsigned,size_t);RangeResult range(int64_t,int64_t,int64_t);}
