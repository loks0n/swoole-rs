// Supplied successful native method facts. Never executes crypto, certificates or IO.
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <sstream>
#include <string>
#include <unordered_map>
#include "swoole_rs_ports.h"
#include "bounds.inc"
static std::ostringstream trace;
using zend_long=int64_t;
struct HashTable;
struct zval {HashTable *array=nullptr;std::string key,bytes;int64_t number=0;bool truth=false,is_null=false;};
struct HashTable : std::unordered_map<std::string,zval> {};
using zend_array=HashTable;
static zval *zend_hash_str_find(HashTable *table,const char *name,size_t length){std::string key(name,length);trace<<"lookup:"<<key<<';';auto i=table->find(key);return i==table->end()?nullptr:&i->second;}
#define ZVAL_IS_NULL(p) ((p)->is_null)
#define php_swoole_array_get_value(ht,str,v) ((v=zend_hash_str_find(ht,str,sizeof(str)-1))&&!ZVAL_IS_NULL(v))
static bool zval_is_true(zval *v){trace<<"bool:"<<v->key<<';';return v->truth;}
static zend_long zval_get_long(zval *v){trace<<"long:"<<v->key<<';';return v->number;}
namespace zend {
struct String {std::string bytes;explicit String(zval *v):bytes(v->bytes){trace<<"string:"<<v->key<<';';}const char *val()const{return bytes.c_str();}std::string to_std_string()const{return bytes;}};
}
#define E_ERROR 1
static void php_swoole_fatal_error(int,const char *,...){assert(false&&"failure/fatal profiles excluded");}
static void text(const char *method,const std::string &value){trace<<method<<':'<<value.size()<<':'<<value<<';';}
static void scalar(const char *method,int64_t value){trace<<method<<':'<<value<<';';}
struct SSLContext {
    unsigned identity=0;
    bool set_cert_file(const std::string &v){assert(!v.empty());text("context-cert",v);return true;}
    bool set_key_file(const std::string &v){assert(!v.empty());text("context-key",v);return true;}
};
struct TlsPort {
    SSLContext context;
    SSLContext *get_ssl_context(){trace<<"context;";return &context;}
    void set_ssl_disable_compress(bool v){scalar("disable-compress",v);}
    void set_ssl_protocols(int64_t v){scalar("protocols",v);}
    void set_ssl_verify_peer(bool v){scalar("verify-peer",v);}
    void set_ssl_allow_self_signed(bool v){scalar("allow-self-signed",v);}
    bool set_ssl_client_cert_file(const std::string &v){assert(!v.empty());text("client-cert",v);return true;}
    void set_ssl_cafile(const std::string &v){text("cafile",v);}
    void set_ssl_capath(const std::string &v){text("capath",v);}
    void set_ssl_verify_depth(int64_t v){scalar("verify-depth",v);}
    void set_ssl_prefer_server_ciphers(bool v){scalar("prefer-ciphers",v);}
    void set_ssl_ciphers(const std::string &v){text("ciphers",v);}
    void set_ssl_ecdh_curve(const std::string &v){text("ecdh",v);}
    void set_ssl_dhparam(const std::string &v){text("dhparam",v);}
};
#ifndef SWR_PORTS_TLS_MODEL_ONLY
namespace Original {
#include "original.inc"
}
namespace Selected {
#include "selected.inc"
}
static uint32_t seed=0x735291;
static uint32_t random_word(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static const char *keys[]={"ssl_cert_file","ssl_key_file","ssl_compress","ssl_protocols","ssl_verify_peer","ssl_allow_self_signed","ssl_client_cert_file","ssl_cafile","ssl_capath","ssl_verify_depth","ssl_prefer_server_ciphers","ssl_ciphers","ssl_ecdh_curve","ssl_dhparam"};
static std::string run(bool selected,HashTable input){
    trace.str("");trace.clear();TlsPort port;auto *context=port.get_ssl_context();
    bool result=selected?Selected::php_swoole_server_set_ssl_option(&input,context):Original::php_swoole_server_set_ssl_option(&input,context);
    assert(result);
    if(selected)Selected::tls_prefix(&port,&input);else Original::tls_prefix(&port,&input);
    return trace.str();
}
int main(){
    size_t cases=0;
    for(unsigned sample=0;sample<4096;sample++){
        HashTable input;
        for(const char *key:keys){auto word=random_word();if((word&3)==0)continue;zval v;v.key=key;v.bytes="fixture-"+v.key+"-"+std::to_string(sample);v.is_null=(word&15)==1;v.truth=(word&32)!=0;const int64_t values[]={INT64_MIN,-1,0,1,255,256,INT64_MAX};v.number=values[(word>>8)%7];input.emplace(key,v);}
        auto expected=run(false,input),actual=run(true,input);
        if(expected!=actual){fprintf(stderr,"TLS frontend model mismatch sample=%u\n",sample);return 1;}cases++;
    }
    for(uint32_t group:{0u,1u})for(size_t index=0;index<16;index++){
        auto option=swr_v1_ports_tls_option(group,index);assert(option.reserved==0&&option.number_kind==0&&option.policy==0);
        if(index<(group==0?2u:12u)){assert(option.key.data&&option.key.len&&option.key.data[option.key.len]==0);assert(option.alias.data&&option.alias.len==0&&option.alias.data[0]==0);assert(option.converter==SWR_PORTS_CONVERT_STRING||option.converter==SWR_PORTS_CONVERT_TRUTH||option.converter==SWR_PORTS_CONVERT_LONG);}
        else assert(option.action==0&&option.key.data==nullptr&&option.alias.data==nullptr);
        cases++;
    }
    for(uint32_t target:{SWR_PORTS_TLS_COMPRESS,SWR_PORTS_TLS_PROTOCOLS,SWR_PORTS_TLS_VERIFY_PEER,SWR_PORTS_TLS_ALLOW_SELF_SIGNED,SWR_PORTS_TLS_VERIFY_DEPTH,SWR_PORTS_TLS_PREFER_CIPHERS})
        for(int64_t value:{INT64_MIN,int64_t(-1),int64_t(0),int64_t(1),int64_t(255),int64_t(256),INT64_MAX}){
            auto actual=swr_v1_ports_tls_value(target,value);int64_t expected=value;
            if(target==SWR_PORTS_TLS_COMPRESS)expected=value==0;
            else if(target==SWR_PORTS_TLS_VERIFY_PEER||target==SWR_PORTS_TLS_ALLOW_SELF_SIGNED||target==SWR_PORTS_TLS_PREFER_CIPHERS)expected=value!=0;
            else if(target==SWR_PORTS_TLS_VERIFY_DEPTH)expected=SW_MAX(0,SW_MIN(value,UINT8_MAX));
            assert(actual==expected);cases++;
        }
    printf("%zu successful TLS frontend model/metadata/scalar comparisons passed; no crypto or IO\n",cases);
    return 0;
}

#endif
