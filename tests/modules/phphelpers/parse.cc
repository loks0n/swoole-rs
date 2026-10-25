// Exact full definition parser; native strings/class lookup/allocation are doubles.
#include <cassert>
#include <cctype>
#include <clocale>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <strings.h>
#include <vector>
#include "swoole_rs_phphelpers.h"
using uchar=unsigned char;
enum { IS_UNDEF=0,IS_NULL=1,IS_FALSE=2,IS_TRUE=3,IS_LONG=4,IS_DOUBLE=5,
       IS_STRING=6,IS_ARRAY=7,IS_OBJECT=8,IS_RESOURCE=9 };
struct zend_string { size_t len;char *val; };
struct zend_class_entry { int identity; };
struct zend_array;
struct zval { zend_class_entry *ce; };
#define Z_OBJCE_P(value) ((value)->ce)
#define SW_STRCASEEQ(value,len,literal) ((len)==sizeof(literal)-1 && strncasecmp(value,literal,len)==0)
static std::vector<std::string> events;
static zend_class_entry initial_ce{1},resolved_ce{2};
static bool class_present,nested_lookup;
static int active_strings;
static std::function<void()> lookup_callback;
static bool instanceof_function(zend_class_entry *actual,zend_class_entry *expected) { return actual==expected; }
static void *emalloc(size_t size) { return std::malloc(size); }
static void zend_throw_error(void *,const char *format,...) {
    char buffer[1024];va_list args;va_start(args,format);std::vsnprintf(buffer,sizeof(buffer),format,args);va_end(args);
    events.push_back(std::string("error:")+buffer);
}
static zend_string *zend_string_alloc(size_t length,bool persistent) {
    assert(!persistent);++active_strings;events.push_back("allocate:"+std::to_string(length)+":"+std::to_string(active_strings));
    auto *result=new zend_string{length,new char[length+1]};result->val[length]=0;return result;
}
static void zend_string_release(zend_string *value) {
    events.push_back("release:"+std::to_string(value->len)+":"+std::to_string(active_strings));
    --active_strings;delete[] value->val;delete value;
}
static zend_string *zend_string_tolower(zend_string *value) {
    events.push_back("lowercase:"+std::to_string(value->len));auto *result=zend_string_alloc(value->len,false);
    for(size_t i=0;i<value->len;++i) {
        const unsigned char byte=value->val[i];
        result->val[i]=byte>='A' && byte<='Z' ? static_cast<char>(byte-'A'+'a') : value->val[i];
    }
    return result;
}
namespace zend {
class String {
    zend_string *storage;
public:
    String(const char *data,size_t length):storage(zend_string_alloc(length,false)) { std::memcpy(storage->val,data,length); }
    ~String() { zend_string_release(storage); }
    zend_string *get() const { return storage; }
    char *val() const { return storage->val; }
};
}
static zend_class_entry *zend_lookup_class(zend_string *name) {
    events.push_back("lookup:"+std::string(name->val,name->len)+":"+std::to_string(active_strings));
    if(lookup_callback && !nested_lookup) {
        nested_lookup=true;lookup_callback();nested_lookup=false;
    }
    return class_present ? &resolved_ce : nullptr;
}
namespace reference {
#include "reference-parse.inc"
}
namespace candidate {
#include "candidate-parse.inc"
}
struct Result { bool accepted;std::vector<std::string> effects;std::vector<unsigned char> metadata; };
template<class Info> static Result run(std::string value,bool present,bool reentry) {
    const size_t capacity=sizeof(Info)+value.size()+1;
    auto *memory=static_cast<unsigned char *>(std::malloc(capacity));std::memset(memory,0xa5,capacity);
    auto *info=reinterpret_cast<Info *>(memory);info->value_ce=&initial_ce;
    zend_string input{value.size(),value.data()};active_strings=0;events.clear();class_present=present;nested_lookup=false;
    lookup_callback=reentry ? std::function<void()>([] {
        events.push_back("reenter");
        auto *nested=static_cast<Info *>(std::malloc(sizeof(Info)+6));std::memset(nested,0xa5,sizeof(Info)+6);
        nested->value_ce=&initial_ce;char text[]="<int>";zend_string input{5,text};
        assert(nested->parse(&input));std::free(nested);events.push_back("resume");
    }) : std::function<void()>();
    const bool accepted=info->parse(&input);assert(active_strings==0);lookup_callback={};
    Result result{accepted,events,{memory,memory+capacity}};std::free(memory);return result;
}
int main() {
    size_t cases=0,locales=0;
    std::vector<std::string> values={"", " ", "int", "<int", "int>", "<>", "<,int>", "<string,>",
        "<int>","<STRING>","<bool>","<resource>","<null>","<float>","<HelperClass>",
        "<int,string>","<string,int>","<<int>>","<int,<string>>","<bool,int>",
        " \t< STRING , INT >\n ",std::string("<in\0t>",sizeof("<in\0t>")-1),std::string("<string,\0int>",sizeof("<string,\0int>")-1),
        std::string("<int,<str\0ing>>",sizeof("<int,<str\0ing>>")-1),"<"+std::string(65532,'a')+">",std::string(65535,'a'),std::string(65536,'b')};
    for(const char *locale:{"C","C.UTF-8","en_US.UTF-8"}) {
        if(!std::setlocale(LC_CTYPE,locale))continue;
        ++locales;
        for(const auto &value:values)for(bool present:{false,true})for(bool reentry:{false,true}) {
            const auto before=run<reference::ArrayTypeInfo>(value,present,reentry);
            const auto after=run<candidate::ArrayTypeInfo>(value,present,reentry);
            if(before.accepted!=after.accepted || before.effects!=after.effects || before.metadata!=after.metadata) {
                std::cerr<<"definition mismatch length="<<value.size()<<" present="<<present<<" reentry="<<reentry<<'\n';
                for(const auto &event:before.effects)std::cerr<<"native "<<event.substr(0,120)<<'\n';
                for(const auto &event:after.effects)std::cerr<<"rust "<<event.substr(0,120)<<'\n';
                return 1;
            }
            ++cases;
        }
    }
    std::cout<<"{\"actual_definition_effect_cases\":"<<cases<<",\"locales\":"<<locales
             <<",\"zend_runtime_executed\":false}\n";
}
