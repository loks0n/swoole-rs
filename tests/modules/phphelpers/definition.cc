// Exact pinned/selected ArrayTypeValue and compaction bodies. No Zend VM execution.
#include <array>
#include <cassert>
#include <cctype>
#include <clocale>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <strings.h>
#include <vector>
#include "swoole_rs_phphelpers.h"
using uchar=unsigned char;
enum { IS_UNDEF=0,IS_NULL=1,IS_FALSE=2,IS_TRUE=3,IS_LONG=4,IS_DOUBLE=5,IS_STRING=6,IS_ARRAY=7,IS_OBJECT=8,IS_RESOURCE=9 };
#define SW_STRCASEEQ(value,len,literal) ((len)==sizeof(literal)-1 && strncasecmp(value,literal,len)==0)
static std::string diagnostic;
static void zend_throw_error(void *,const char *format,const char *name) {
    char buffer[1024];std::snprintf(buffer,sizeof(buffer),format,name);diagnostic=buffer;
}
struct zend_string { size_t len;char *val; };
static std::vector<size_t> allocations;
static zend_string *zend_string_alloc(size_t length,bool persistent) {
    assert(!persistent);allocations.push_back(length);
    auto *result=new zend_string{length,new char[length+1]};
    std::memset(result->val,0xa5,length+1);return result;
}
namespace reference {
struct ArrayTypeValue { uint8_t type_of_value=7,type_of_key=5;uint16_t offset_of_value_type_str=77,len_of_value_type_str=88;bool parse(const char *,size_t); };
struct ArrayTypeInfo {
    uint8_t key;std::string value;
    uint8_t get_type_of_key() const {return key;}
    uint16_t get_len_of_value_type_str() const {return value.size();}
    const char *get_value_type_str() const {return value.data();}
};
#include "reference-definition.inc"
}
namespace candidate {
struct ArrayTypeValue { uint8_t type_of_value=7,type_of_key=5;uint16_t offset_of_value_type_str=77,len_of_value_type_str=88;bool parse(const char *,size_t); };
struct ArrayTypeInfo {
    uint8_t key;std::string value;
    uint8_t get_type_of_key() const {return key;}
    uint16_t get_len_of_value_type_str() const {return value.size();}
    const char *get_value_type_str() const {return value.data();}
};
#include "candidate-definition.inc"
}
template<class Info> static std::string parse(const std::string &value,size_t logical=SIZE_MAX) {
    Info info;diagnostic.clear();const bool ok=info.parse(value.c_str(),logical==SIZE_MAX ? value.size() : logical);
    std::ostringstream result;result<<ok<<':'<<unsigned(info.type_of_key)<<':'<<unsigned(info.type_of_value)<<':'
        <<info.offset_of_value_type_str<<':'<<info.len_of_value_type_str<<':'<<diagnostic;return result.str();
}
int main() {
    size_t cases=0,normalizations=0,locales=0,byte_cases=0,projections=0,span_cases=0;
    std::ostringstream profiles;bool first=true;
    for(const char *locale:{"C","C.UTF-8","en_US.UTF-8"}) {
        const bool available=std::setlocale(LC_CTYPE,locale)!=nullptr;
        if(!first)profiles<<',';
        first=false;profiles<<"{\"name\":\""<<locale<<"\",\"available\":"<<(available?"true":"false")<<'}';
        if(!available) continue;
        ++locales;
        for(const std::string value:{"<int>","<float>","<string>","<bool>","<resource>","<null>","<SampleClass>",
                                     "<int,string>","<string,int>","<int,<string>>","<string,<int>>",
                                     "<bool,int>","<float,string>","<INT,STRING>"}) {
            const auto before=parse<reference::ArrayTypeValue>(value),after=parse<candidate::ArrayTypeValue>(value);
            if(before!=after){std::cerr<<value<<'\n'<<before<<'\n'<<after<<'\n';return 1;}++cases;
            const std::string spaced=" \t"+value+"\n ";
            std::array<char,256> a{},b{};std::memcpy(a.data(),spaced.data(),spaced.size());b=a;
            char *pa=a.data(),*pb=b.data();uint16_t la=spaced.size(),lb=spaced.size();
            reference::remove_all_spaces(&pa,&la);candidate::remove_all_spaces(&pb,&lb);
            assert(la==lb && pa-a.data()==pb-b.data() && a==b);++normalizations;
        }
        // Compare the complete pinned/selected body, including output fields
        // and diagnostics, when initialized logical bytes extend beyond NUL.
        for(const std::string &base:{std::string("<int>"),std::string("<string,int>"),
                                    std::string("<bool,string>"),std::string("<int,<string>>")}) {
            for(size_t position=1;position+1<base.size();++position) {
                auto value=base;value[position]='\0';
                const auto before=parse<reference::ArrayTypeValue>(value);
                const auto after=parse<candidate::ArrayTypeValue>(value);
                if(before!=after){std::cerr<<"initialized-span mismatch at "<<position<<'\n';return 1;}
                // A nonzero result proves these witnesses actually use the new
                // Rust projection rather than merely agreeing through fallback.
                SwrPhpTypeLayout plan{};
                assert(swr_v1_phphelpers_type_span(reinterpret_cast<const uint8_t *>(value.c_str()),
                                                  value.size()+1,value.size(),&plan)!=0);
                ++span_cases;
            }
        }
        for(const std::string &value:{std::string("<int>>"),std::string("<string,int>>"),
                                     std::string("<int,<string>>>"),std::string("<bool,int>>")}) {
            const auto logical=value.size()-1;
            assert(parse<reference::ArrayTypeValue>(value,logical)==parse<candidate::ArrayTypeValue>(value,logical));
            SwrPhpTypeLayout plan{};
            assert(swr_v1_phphelpers_type_span(reinterpret_cast<const uint8_t *>(value.c_str()),
                                              value.size()+1,logical,&plan)!=0);
            ++span_cases;
        }
        // Initialized byte extents exercise host ctype semantics independently
        // of the definition parser and contain no Zend/VM storage.
        for(unsigned byte=0;byte<256;++byte) {
            std::array<char,7> a{{'a',static_cast<char>(byte),'b',' ',static_cast<char>(byte),'c','\0'}},b=a;
            char *pa=a.data(),*pb=b.data();uint16_t la=6,lb=6;
            reference::remove_all_spaces(&pa,&la);candidate::remove_all_spaces(&pb,&lb);
            assert(la==lb && pa-a.data()==pb-b.data() && a==b);++byte_cases;
        }
    }
    for(uint8_t key:{IS_UNDEF,IS_LONG,IS_STRING}) {
        for(const std::string &value:{std::string("int"),std::string("string"),std::string("HelperValue"),
                                     std::string("<string,int>"),std::string(256,'a'),std::string(4096,'b')}) {
            reference::ArrayTypeInfo before_info{key,value};candidate::ArrayTypeInfo after_info{key,value};
            allocations.clear();auto *before=reference::get_array_type_def(&before_info);const auto before_allocations=allocations;
            allocations.clear();auto *after=candidate::get_array_type_def(&after_info);
            assert(before_allocations==allocations && allocations.size()==1 && before->len==after->len);
            assert(std::memcmp(before->val,after->val,allocations[0]+1)==0);
            delete[] before->val;delete before;delete[] after->val;delete after;++projections;
        }
    }
    for(uint32_t kind=0;kind<=9;++kind) {
        assert(swr_v1_phphelpers_operation(kind,1)==(kind==SWR_PHP_STRING ? 0u : 1u));
        assert(swr_v1_phphelpers_operation(kind,0)==(kind==SWR_PHP_LONG || kind==SWR_PHP_DOUBLE ? 0u : 2u));
    }
    for(uint32_t kind=0;kind<=9;++kind) {
        const int expected=kind==SWR_PHP_ARRAY ? 0 : kind==SWR_PHP_STRING ? 1 : kind==SWR_PHP_RESOURCE ? 2 : -1;
        assert(swr_v1_phphelpers_method_family(kind)==expected);
    }
    for(uint8_t typed:{0,1})for(uint8_t list:{0,1}) {
        assert(swr_v1_phphelpers_opcode(0,typed,list)==(typed ? 1u : 0u));
        assert(swr_v1_phphelpers_opcode(1,typed,list)==(typed ? 2u : 0u));
        assert(swr_v1_phphelpers_opcode(2,typed,list)==(typed && list ? 3u : 0u));
    }
    for(int64_t options:{INT64_MIN,int64_t(-1),int64_t(0),int64_t(3),INT64_MAX})for(uint8_t assoc:{0,1}) {
        assert(swr_v1_phphelpers_json_options(options,1,assoc)==(assoc ? options|1 : options&~int64_t(1)));
    }
    std::cout<<"{\"actual_type_value_cases\":"<<cases<<",\"actual_normalization_cases\":"<<normalizations<<",\"locales\":"<<locales<<",\"actual_definition_projections\":"<<projections<<",\"actual_initialized_span_cases\":"<<span_cases<<",\"actual_byte_compaction_cases\":"<<byte_cases<<",\"locale_profiles\":["<<profiles.str()<<"]}\n";
}
