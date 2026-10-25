// Complete pinned/selected ArrayTypeInfo::check bodies with native-effect doubles.
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum { IS_UNDEF=0, IS_NULL=1, IS_FALSE=2, IS_TRUE=3, IS_LONG=4,
       IS_DOUBLE=5, IS_STRING=6, IS_ARRAY=7, IS_OBJECT=8, IS_RESOURCE=9, IS_REFERENCE=10 };
enum { HASH_FLAG_TYPED_ARRAY=1<<12 };
struct zend_string { size_t len; char *val; };
struct zend_class_entry { zend_string *name; };
struct zend_array { uint32_t flags, count; };
using HashTable=zend_array;
struct zval { uint8_t type; int64_t number; zend_array *array; zend_class_entry *ce; const zval *reference; };
#define Z_TYPE_P(z) ((z)->type)
#define Z_LVAL_P(z) ((z)->number)
#define Z_ARRVAL_P(z) ((z)->array)
#define Z_OBJCE_P(z) ((z)->ce)
#define ZVAL_DEREF(z) do { if ((z)->type==IS_REFERENCE) (z)=(z)->reference; } while (false)
#define ZVAL_IS_BOOL(z) ((z)->type==IS_TRUE || (z)->type==IS_FALSE)
#define HT_FLAGS(ht) ((ht)->flags)
#define ZSTR_LEN(s) ((s)->len)
#define ZSTR_VAL(s) ((s)->val)
static std::vector<std::string> effects;
static uint32_t zend_hash_num_elements(const zend_array *array) { effects.push_back("count"); return array->count; }
static const char *zend_get_type_by_const(uint8_t kind) {
    static const char *names[]={"undef","null","bool","bool","int","float","string","array","object","resource","reference"};
    return names[kind];
}
static void diagnostic(const char *prefix,const char *format,va_list arguments) {
    char buffer[1024];std::vsnprintf(buffer,sizeof(buffer),format,arguments);
    effects.push_back(std::string(prefix)+buffer);
}
static void zend_type_error(const char *format,...) {
    va_list arguments;va_start(arguments,format);diagnostic("type:",format,arguments);va_end(arguments);
}
static void zend_throw_error(void *,const char *format,...) {
    va_list arguments;va_start(arguments,format);diagnostic("error:",format,arguments);va_end(arguments);
}
static bool instanceof_function(zend_class_entry *actual,zend_class_entry *expected) {
    effects.push_back("instance");return actual==expected;
}
static void *emalloc(size_t size) { return std::malloc(size); }
static zend_string *zend_string_alloc(size_t size,bool persistent) {
    assert(!persistent);effects.push_back("allocate:"+std::to_string(size));
    return new zend_string{size,new char[size+1]};
}
static void zend_string_release(zend_string *value) {
    effects.push_back("release");delete[] value->val;delete value;
}
namespace reference {
#include "reference-validation.inc"
}
namespace candidate {
#include "candidate-validation.inc"
}
template<class Info> struct Array {
    zend_array *array;
    Info *info;
    Array(uint8_t key,uint8_t value,const char *definition,uint16_t offset) {
        const size_t length=std::strlen(definition);
        array=static_cast<zend_array *>(std::calloc(1,sizeof(zend_array)+sizeof(Info)+length+1));
        array->flags=HASH_FLAG_TYPED_ARRAY;array->count=3;
        info=reinterpret_cast<Info *>(reinterpret_cast<char *>(array)+sizeof(zend_array));
        info->self.type_of_key=key;info->self.type_of_value=value;
        info->self.offset_of_value_type_str=offset;info->self.len_of_value_type_str=length-offset-1;
        info->element.type_of_key=IS_UNDEF;info->element.type_of_value=IS_LONG;
        info->len_of_type_str=length;std::memcpy(info->type_str,definition,length+1);
    }
    ~Array() { std::free(array); }
};
template<class Info> static std::vector<std::string> run(
    uint8_t key_kind,uint8_t value_kind,zval key,uint8_t actual,bool reference_value,int nested,bool matching_class) {
    Array<Info> source(key_kind,value_kind,"<<int>>",1);
    Array<Info> child(IS_UNDEF,nested==2 ? IS_STRING : IS_LONG,nested==2 ? "<string>" : "<int>",1);
    if(nested==0)child.array->flags=0;
    char expected_name[]="Expected",actual_name[]="Actual";
    zend_string expected_string{8,expected_name},actual_string{6,actual_name};
    zend_class_entry expected_ce{&expected_string},actual_ce{&actual_string};
    source.info->value_ce=&expected_ce;
    zval value{actual,0,child.array,matching_class ? &expected_ce : &actual_ce,nullptr};
    zval wrapper{IS_REFERENCE,0,nullptr,nullptr,&value};
    effects.clear();
    const bool accepted=source.info->check(source.array,&key,reference_value ? &wrapper : &value);
    effects.push_back(accepted ? "accepted" : "rejected");return effects;
}
int main() {
    size_t cases=0;
    const std::vector<zval> keys={{IS_UNDEF,0,nullptr,nullptr,nullptr},{IS_NULL,0,nullptr,nullptr,nullptr},
        {IS_LONG,-1,nullptr,nullptr,nullptr},{IS_LONG,0,nullptr,nullptr,nullptr},
        {IS_LONG,4,nullptr,nullptr,nullptr},{IS_STRING,0,nullptr,nullptr,nullptr},{IS_DOUBLE,0,nullptr,nullptr,nullptr}};
    for(uint8_t expected_key:{IS_UNDEF,IS_LONG,IS_STRING})
    for(uint8_t expected_value:{IS_NULL,IS_FALSE,IS_TRUE,IS_LONG,IS_DOUBLE,IS_STRING,IS_ARRAY,IS_OBJECT,IS_RESOURCE})
    for(const auto key:keys)for(uint8_t actual=0;actual<=IS_RESOURCE;++actual)
    for(bool ref:{false,true})for(int nested:{0,1,2})for(bool matching_class:{false,true}) {
        const auto before=run<reference::ArrayTypeInfo>(expected_key,expected_value,key,actual,ref,nested,matching_class);
        const auto after=run<candidate::ArrayTypeInfo>(expected_key,expected_value,key,actual,ref,nested,matching_class);
        if(before!=after) {
            std::cerr<<"validation mismatch "<<unsigned(expected_key)<<':'<<unsigned(expected_value)<<':'
                     <<unsigned(key.type)<<':'<<unsigned(actual)<<':'<<ref<<':'<<nested<<':'<<matching_class<<'\n';
            for(const auto &event:before)std::cerr<<"native "<<event<<'\n';
            for(const auto &event:after)std::cerr<<"rust "<<event<<'\n';
            return 1;
        }
        ++cases;
    }
    std::cout<<"{\"actual_validation_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
