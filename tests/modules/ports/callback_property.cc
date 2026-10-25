// Exact PHP method bodies with initialized normal value/property models.
// Conversion/property/return order is observed; removed allocations are explicit.
#include <cassert>
#include <clocale>
#include <cstdio>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_ports.h"
#include "zend-map.inc"
#include "events.inc"
static std::ostringstream trace;
static unsigned lowercase_calls;
struct zval { std::string bytes; bool is_null=false; unsigned identity=0; };
struct zend_string { std::string bytes; };
namespace zend {
class String {
    zend_string storage;
  public:
    explicit String(zval *input) { trace << "convert;"; storage.bytes=input->bytes; }
    String(zend_string *input,bool) { storage.bytes=std::move(input->bytes); delete input; }
    zend_string *get() { return &storage; }
    const char *val() const { return storage.bytes.data(); }
    size_t len() const { return storage.bytes.size(); }
    std::string to_std_string() const { return storage.bytes; }
};
}
static zend_string *zend_string_tolower(zend_string *input) {
    lowercase_calls++;
    auto *result=new zend_string{input->bytes};
    for(char &c:result->bytes)c=static_cast<char>(zend_lowercase[static_cast<unsigned char>(c)]);
    return result;
}
static std::unordered_map<std::string,zval> properties;
static int object,entry;
static int *swoole_server_port_ce=&entry;
static zval null_value{"",true,0};
static zval *zend_read_property(int *ce,int *obj,const char *name,size_t size,bool silent,zval *) {
    assert(ce==swoole_server_port_ce&&obj==&object&&silent);
    trace << "read:" << std::string(name,size) << ';';
    auto i=properties.find(std::string(name,size));return i==properties.end()?&null_value:&i->second;
}
#define PHP_METHOD(c,m) zval *getCallback(zval *input)
#define ZEND_PARSE_PARAMETERS_START(a,b)
#define Z_PARAM_ZVAL(name) name=input;
#define ZEND_PARSE_PARAMETERS_END_EX(fallback)
#define ZEND_THIS (&object)
#define SW_Z8_OBJ_P(p) (p)
#define ZVAL_IS_NULL(p) ((p)->is_null)
#define RETURN_FALSE return nullptr
#define RETURN_NULL() do {trace << "null;";return nullptr;}while(0)
#define RETURN_ZVAL(p,copy,dtor) do {static_assert(copy==1&&dtor==0,"return flags");trace << "copy:" << (p)->identity << ';';return (p);}while(0)
namespace Original {
#include "original.inc"
}
namespace Selected {
#include "selected.inc"
}
static uint32_t seed=0x81715;
static uint32_t random_word(){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static unsigned long cases;
static void compare(const std::string &name,bool null_properties) {
    unsigned id=1;properties.clear();
    for(const auto &event:server_port_event_map) properties.emplace("on"+event.second.name,zval{"callback",null_properties,id++});
    zval input{name,false,0};
    trace.str("");trace.clear();lowercase_calls=0;auto *expected=Original::getCallback(&input);auto original=trace.str();assert(lowercase_calls==1);
    trace.str("");trace.clear();lowercase_calls=0;auto *actual=Selected::getCallback(&input);assert(lowercase_calls==0);
    if(expected!=actual||original!=trace.str()) {fprintf(stderr,"getter model mismatch case=%lu length=%zu\n",cases,name.size());std::abort();}
    cases++;
}
int main() {
    std::vector<std::string> names={"","unknown",std::string("connect\0",8),"receive-extra"};
    for(const auto &event:server_port_event_map) {
        names.push_back(event.first);auto upper=event.first;
        for(char &c:upper)c=c>='a'&&c<='z'?c-32:c;
        names.push_back(upper);
        for(size_t p=0;p<event.first.size();p++) for(unsigned c=0;c<256;c++) {
            auto name=upper;name[p]=static_cast<char>(c);names.push_back(name);
        }
    }
    for(unsigned n=0;n<4096;n++) {std::string name(random_word()%64,'\0');for(char &c:name)c=static_cast<char>(random_word());names.push_back(name);}
    unsigned locales=0;
    for(const char *locale:{"C","","tr_TR.UTF-8"}) {
        if(!setlocale(LC_CTYPE,locale))continue;
        locales++;
        for(const auto &name:names) for(bool null_properties:{false,true})compare(name,null_properties);
    }
    assert(locales>=1);
    printf("%lu exact normal getter comparisons; %u available locale settings; native lowercase allocation removed\n",cases,locales);
}
