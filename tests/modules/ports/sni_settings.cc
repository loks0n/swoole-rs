// Stable valid native mappings and supplied successful context effects; no actual TLS.
#define SWR_PORTS_TLS_MODEL_ONLY
#include "tls_settings.cc"
#include <memory>
#include <vector>
using zend_ulong=uint64_t;
struct zend_string {const char *val;size_t len;};
#define IS_ARRAY 7
#define Z_TYPE_P(v) ((v)->array ? IS_ARRAY : 0)
#define Z_ARRVAL_P(v) ((v)->array)
#define E_WARNING 2
#define RETURN_FALSE return false
#define ZEND_HASH_FOREACH_KEY_VAL(ht,key_index,key,current) \
    for(auto &_node:*(ht)) \
        for(zend_string _stored{_node.first.data(),_node.first.size()},*_once=&_stored;_once;_once=nullptr) \
            for(bool _bound=((key_index)=0,(key)=&_stored,(current)=&_node.second,true);_bound;_bound=false)
#define ZEND_HASH_FOREACH_END()
struct SniPort : TlsPort {
    unsigned counter=0;
    std::shared_ptr<SSLContext> dup_ssl_context(){auto ctx=std::make_shared<SSLContext>();ctx->identity=++counter;trace<<"dup:"<<ctx->identity<<';';return ctx;}
    bool ssl_add_sni_cert(const std::string &name,const std::shared_ptr<SSLContext> &ctx){text("add-name",name);trace<<"add-context:"<<ctx->identity<<';';return true;}
};
namespace Original {
#include "original.inc"
}
namespace Selected {
#include "selected.inc"
}
static uint32_t seed=0x756120;
static uint32_t random_word(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static std::string run(bool selected,HashTable input){trace.str("");trace.clear();SniPort port;bool result=selected?Selected::sni_prefix(&port,&input):Original::sni_prefix(&port,&input);assert(result);trace<<"contexts:"<<port.counter<<';';return trace.str();}
int main(){
    static_assert(sizeof(SwrPortsSniPlan)==24&&offsetof(SwrPortsSniPlan,status)==16,"SNI plan ABI");
    size_t cases=0;
    for(unsigned sample=0;sample<1024;sample++){
        HashTable input,hosts;std::vector<std::unique_ptr<HashTable>> children;
        for(unsigned n=0;n<sample%5;n++){
            auto child=std::make_unique<HashTable>();
            for(const char *key:{"ssl_cert_file","ssl_key_file"}){auto word=random_word();if((word&3)==0)continue;zval value;value.key=key;value.bytes="fixture-"+value.key+"-"+std::to_string(sample);value.is_null=(word&15)==1;child->emplace(key,value);}
            zval node;node.key="host";node.array=child.get();hosts.emplace("host"+std::to_string(n)+".example",node);children.push_back(std::move(child));
        }
        if(sample%7){zval mapping;mapping.key="ssl_sni_certs";mapping.array=&hosts;mapping.is_null=sample%11==0;input.emplace(mapping.key,mapping);}
        auto expected=run(false,input),actual=run(true,input);if(expected!=actual){fprintf(stderr,"SNI frontend trace mismatch sample=%u\n",sample);return 1;}cases++;
    }
    auto name=swr_v1_ports_sni_plan(0,0,0);assert(name.status==0&&name.reserved==0&&std::string((const char*)name.key.data,name.key.len)=="ssl_sni_certs"&&name.key.data[name.key.len]==0);cases++;
    for(uint32_t stage:{1u,2u})for(uint32_t key:{0u,1u})for(uint32_t array:{0u,1u}){
        auto plan=swr_v1_ports_sni_plan(stage,key,array);assert(plan.key.data==nullptr&&plan.key.len==0&&plan.reserved==0);
        auto status=stage==1?(array?0u:1u):(!key?2u:!array?3u:0u);assert(plan.status==status);cases++;
    }
    printf("%zu valid SNI frontend mapping and candidate-only admission comparisons passed; no matching/crypto/IO\n",cases);
    return 0;
}
