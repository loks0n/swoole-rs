/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
// DECLARATIONS
namespace BODY_NAMESPACE {
enum {IS_UNDEF, IS_OBJECT, IS_STRING, IS_ARRAY, IS_LONG};
struct Value {std::string bytes; long number=0; Value *host=nullptr,*port=nullptr;int host_type=IS_STRING,port_type=IS_LONG;};
struct zval {int type;Value *value;};
struct NameResolver {struct Context {void *private_data=nullptr;void(*dtor)(Context*)=nullptr;bool with_port=false,final_=false,cluster_=false;};};
static NameResolver::Context *active;static unsigned bits,mutation;static int fail_at,events;
static std::ostringstream trace;static std::vector<std::unique_ptr<Value>> values;static std::vector<void*> allocated;
static Value *value(std::string s="",long n=0){auto p=std::make_unique<Value>();p->bytes=s;p->number=n;auto out=p.get();values.push_back(std::move(p));return out;}
static void event(const char *name){trace<<name<<':'<<(active->private_data!=nullptr)<<active->with_port<<active->final_<<active->cluster_<<';';if(events++==fail_at)throw std::runtime_error(name);}
static void mutate(unsigned point){
 if((mutation==9&&point==1)||(mutation==10&&point==2)){auto p=std::calloc(1,sizeof(zval));if(!p)throw std::bad_alloc();allocated.push_back(p);auto z=static_cast<zval*>(p);z->type=IS_OBJECT;z->value=value("replacement");active->private_data=z;}
 if(mutation==11&&point==3)active->private_data=nullptr;
 if(mutation==point){active->with_port=!active->with_port;active->final_=!active->final_;active->cluster_=!active->cluster_;}}
static void zval_dtor(zval *z){event(z->type==IS_STRING?"dtor-string":z->type==IS_OBJECT?"dtor-object":"dtor-other");mutate(6);}
static void zval_ptr_dtor(zval*z){event("ptr-dtor");mutate(7);z->type=IS_UNDEF;}
static void *ecalloc(size_t n,size_t size){event("ecalloc");auto p=std::calloc(n,size);if(!p)throw std::bad_alloc();allocated.push_back(p);return p;}
static void efree(void *p){event("efree");for(auto &item:allocated)if(item==p){std::free(p);item=nullptr;return;}assert(false);}
static void make_name(zval*z,const char*p,size_t n){event("name");trace<<n<<';';z->type=IS_STRING;z->value=value(std::string(p,n));}
static long zval_get_long(zval*z){event("get-long");mutate(5);return z->value->number;}
static void zend_call_method_with_1_params(zval*,void*,void*,const char*,zval*out,zval*name){event("lookup");trace<<name->value->bytes.size()<<';';mutate(1);switch((bits>>1)%3){case 0:out->type=IS_UNDEF;break;case 1:out->type=IS_STRING;break;case 2:out->type=IS_OBJECT;break;}out->value=value(std::string("node\0tail",9));}
static void sw_zend_call_method_with_0_params(zval*,void*,void*,const char*method,zval*out){
 event(method);if(std::strcmp(method,"count")==0){mutate(2);out->type=IS_LONG;out->value=value("",(bits>>3)&1);return;}
 mutate(3);unsigned host=(bits>>4)&3,port=(bits>>6)&3;out->type=host?IS_ARRAY:IS_UNDEF;out->value=value();
 if(host>=2){out->value->host=value(std::string("host\0x",6));out->value->host_type=host==3?IS_STRING:IS_LONG;}
 if(port){out->value->port=value("port",port==1?-9223372036854775807L:port==2?0:65536);out->value->port_type=port==3?IS_STRING:IS_LONG;}
}
static zval *zend_hash_str_find(Value*v,const char *key,size_t){static zval found;event(key);mutate(std::strcmp(key,"host")==0?4:8);if(std::strcmp(key,"host")==0){if(!v->host)return nullptr;found={v->host_type,v->host};}else{if(!v->port)return nullptr;found={v->port_type,v->port};}return &found;}
#define ZVAL_STRINGL(z,p,n) make_name(z,p,n)
#define Z_TYPE(z) ((z).type)
#define Z_STRVAL(z) ((z).value->bytes.data())
#define Z_STRLEN(z) ((z).value->bytes.size())
#define Z_STRVAL_P(z) Z_STRVAL(*(z))
#define Z_STRLEN_P(z) Z_STRLEN(*(z))
#define ZVAL_IS_ARRAY(z) ((z)->type==IS_ARRAY)
#define ZVAL_IS_STRING(z) ((z)->type==IS_STRING)
#define SW_Z8_OBJ_P(z) (z)
#define HASH_OF(z) ((z)->value)
#define ZEND_STRL(z) z,sizeof(z)-1
// ACTUAL_BODY
static std::string run(unsigned input,unsigned mut,int fail){
 bits=input;mutation=mut;fail_at=fail;events=0;trace.str("");trace.clear();values.clear();allocated.clear();NameResolver::Context ctx;active=&ctx;
 ctx.with_port=(bits>>8)&1;ctx.final_=(bits>>9)&1;ctx.cluster_=(bits>>10)&1;
 ctx.dtor=[](NameResolver::Context*c){zval_dtor((zval*)c->private_data);efree(c->private_data);};
 if(bits&1){auto p=std::calloc(1,sizeof(zval));allocated.push_back(p);auto z=static_cast<zval*>(p);z->type=IS_OBJECT;z->value=value();ctx.private_data=z;}
 zval resolver={IS_OBJECT,value()};std::string result,status="ok";
 try{result=php_swoole_name_resolver_lookup(std::string("name\0query",10),&ctx,&resolver);}catch(const std::exception&e){status=e.what();}
 std::ostringstream answer;answer<<trace.str()<<'|'<<status<<'|'<<(ctx.private_data!=nullptr)<<ctx.with_port<<ctx.final_<<ctx.cluster_<<'|';for(unsigned char c:result)answer<<std::hex<<unsigned(c)<<',';
 size_t live=0;for(auto p:allocated)if(p){++live;std::free(p);}answer<<"|live="<<live;values.clear();active=nullptr;return answer.str();
}
}
// DRIVER
