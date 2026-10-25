// Complete public construction/predicate bodies, modeled Zend storage/effects.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum {IS_UNDEF=0,IS_NULL=1,IS_FALSE=2,IS_TRUE=3,IS_LONG=4,IS_STRING=6,IS_ARRAY=7,HASH_FLAG_TYPED_ARRAY=1};
struct zend_string {size_t length;const char *value;};
struct zend_array;
struct zval {int type,number,refs;zend_array *array;zend_string *string;};
using zend_ulong=unsigned long;
struct Entry {zend_ulong index;zend_string *key;zval value;};
struct zend_array {uint32_t flags;std::vector<Entry> *entries;};
using HashTable=zend_array;
struct Interrupted {};
struct Config {bool parse,equal,nested,element;int reject;};
static Config config;
static std::vector<std::string> events;
static std::vector<void *> storage;
static std::deque<std::vector<Entry>> tables;
static int effect,fail_at,checks;
static zend_string definition{5,"<int>"},string_key{3,"key"};
static zend_string *input_definition;
static zval *input_values;
static void tick(const std::string &name) {events.push_back(name);if(effect++==fail_at)throw Interrupted{};}
static void *allocate(size_t size) {void *p=::operator new(size);std::memset(p,0xcc,size);storage.push_back(p);return p;}
static void *emalloc(size_t size) {tick("allocate:"+std::to_string(size));return allocate(size);}
static void efree(void *) {tick("free");}
struct ArrayTypeValue {
    uint8_t type_of_value;
    bool parse(const char *,size_t) {tick("element-parse");type_of_value=IS_LONG;return config.element;}
};
struct ArrayTypeInfo {
    ArrayTypeValue self,element;uint16_t len_of_type_str;char type_str[0];
    bool parse(zend_string *) {
        tick("definition-parse");if(!config.parse)return false;
        self.type_of_value=config.nested?IS_ARRAY:IS_LONG;element.type_of_value=IS_UNDEF;
        len_of_type_str=5;std::memcpy(type_str,"<int>",6);return true;
    }
    bool equals(const ArrayTypeInfo *)const {tick("metadata-equal");return config.equal;}
    const char *get_value_type_str()const {return type_str;}
    uint16_t get_len_of_value_type_str()const {return len_of_type_str;}
    bool check(const zend_array *,const zval *key,const zval *value)const {
        tick("check:"+std::to_string(key->type)+":"+std::to_string(value->number));return checks++!=config.reject;
    }
};
#define ZSTR_LEN(s) ((s)->length)
#define Z_ARRVAL_P(z) ((z)->array)
#define ZVAL_IS_ARRAY(z) ((z)->type==IS_ARRAY)
#define HT_FLAGS(ht) ((ht)->flags)
#define ZVAL_PTR_DTOR nullptr
#define PHP_FUNCTION(name) void name(zval *return_value)
#define ZEND_PARSE_PARAMETERS_START(minimum,maximum) do {
#define Z_PARAM_STR(name) name=input_definition;
#define Z_PARAM_OPTIONAL
#define Z_PARAM_ARRAY(name) name=input_values;
#define ZEND_PARSE_PARAMETERS_END() } while(0)
static void publish(zval *value,int type) {tick("publish:"+std::to_string(type));value->type=type;}
#define RETURN_NULL() do {publish(return_value,IS_NULL);return;} while(0)
#define RETURN_FALSE do {publish(return_value,IS_FALSE);return;} while(0)
#define RETURN_TRUE do {publish(return_value,IS_TRUE);return;} while(0)
#define RETVAL_BOOL(value) publish(return_value,(value)?IS_TRUE:IS_FALSE)
static void copy(zval *output,zval *source) {tick("copy-initial");*output=*source;++output->refs;}
#define ZVAL_COPY(output,source) copy(output,source)
static void publish_array(zval *output,zend_array *array) {tick("publish-array");output->type=IS_ARRAY;output->array=array;}
#define ZVAL_ARR(output,array) publish_array(output,array)
static void key_string(zval *key,zend_string *string) {tick("key-string");key->type=IS_STRING;key->string=string;}
#define ZVAL_STR(key,string) key_string(key,string)
static void key_index(zval *key,zend_ulong index) {tick("key-index:"+std::to_string(index));key->type=IS_LONG;key->number=int(index);}
#define ZVAL_LONG(key,index) key_index(key,index)
static void zval_ptr_dtor(zval *) {tick("destroy-output");}
static void addref(zval *value) {tick("addref:"+std::to_string(value->number));++value->refs;}
#define Z_TRY_ADDREF_P(value) addref(value)
static void zend_throw_error(void *,const char *message) {tick(std::string("error:")+message);}
static size_t zend_array_count(zend_array *array) {tick("initial-count");return array->entries->size();}
static void _zend_hash_init(HashTable *array,uint32_t size,void *,bool persistent) {
    assert(!persistent);tick("hash-init:"+std::to_string(size));tables.emplace_back();array->entries=&tables.back();array->flags=0;
}
static void zend_hash_add(HashTable *array,zend_string *key,zval *value) {tick("insert-string:"+std::to_string(value->number));array->entries->push_back({0,key,*value});}
static void zend_hash_index_add(HashTable *array,zend_ulong key,zval *value) {tick("insert-index:"+std::to_string(key)+":"+std::to_string(value->number));array->entries->push_back({key,nullptr,*value});}
#define ZEND_HASH_FOREACH_KEY_VAL(TABLE,NUMOUT,STROUT,ZVOUT) for(size_t fixture_index=0;fixture_index<(TABLE)->entries->size();++fixture_index) {auto &fixture_entry=(*(TABLE)->entries)[fixture_index];NUMOUT=fixture_entry.index;STROUT=fixture_entry.key;ZVOUT=&fixture_entry.value;
#define ZEND_HASH_FOREACH_END() }
namespace reference {
#include "reference-construction.inc"
}
namespace candidate {
#include "candidate-construction.inc"
}
using Function=void (*)(zval *);
static std::vector<std::string> run(Function fn,bool predicate,int initial,int count,int keys,uint32_t flags,int rejected,int failure) {
    for(void *p:storage) {::operator delete(p);}storage.clear();tables.clear();events.clear();checks=0;effect=0;fail_at=failure;
    config={bool(flags&1),bool(flags&2),bool(flags&4),bool(flags&8),rejected};
    auto *source=static_cast<HashTable *>(allocate(sizeof(HashTable)+sizeof(ArrayTypeInfo)+6));
    tables.emplace_back();source->entries=&tables.back();source->flags=initial==2?HASH_FLAG_TYPED_ARRAY:0;
    auto *metadata=reinterpret_cast<ArrayTypeInfo *>(reinterpret_cast<char *>(source)+sizeof(HashTable));
    metadata->self.type_of_value=IS_LONG;metadata->element.type_of_value=IS_UNDEF;metadata->len_of_type_str=5;std::memcpy(metadata->type_str,"<int>",6);
    for(int index=0;index<count;++index)source->entries->push_back({zend_ulong(index+2),keys==1||(keys==2&&index%2)?&string_key:nullptr,{IS_LONG,index+10,1,nullptr,nullptr}});
    zval input{IS_ARRAY,0,1,source,nullptr};input_values=predicate||initial!=0?&input:nullptr;input_definition=predicate&&keys==0?nullptr:&definition;
    zval result{IS_UNDEF,0,1,nullptr,nullptr};
    try {fn(&result);events.push_back("return");}catch(const Interrupted &){events.push_back("interrupted");}
    events.push_back("result:"+std::to_string(result.type)+":"+std::to_string(result.refs));
    if(result.type==IS_ARRAY) {
        events.push_back("source-identity:"+std::to_string(result.array==source));
        events.push_back("flags:"+std::to_string(result.array->flags));
        const auto *info=reinterpret_cast<const ArrayTypeInfo *>(reinterpret_cast<const char *>(result.array)+sizeof(HashTable));
        events.push_back("metadata:"+std::to_string(info->self.type_of_value)+":"+std::to_string(info->element.type_of_value)+":"+std::to_string(info->len_of_type_str));
        for(auto &entry:*result.array->entries)events.push_back("entry:"+std::to_string(entry.key!=nullptr)+":"+std::to_string(entry.index)+":"+std::to_string(entry.value.number)+":"+std::to_string(entry.value.refs));
    }
    for(auto &entry:*source->entries) {events.push_back("input-ref:"+std::to_string(entry.value.refs));}
    return events;
}
int main() {
    size_t constructions=0,predicates=0;
    for(int initial=0;initial<3;++initial)for(int count=0;count<4;++count)for(int keys=0;keys<3;++keys)
        for(uint32_t flags=0;flags<16;++flags)for(int rejected=-1;rejected<3;++rejected)for(int failure=-1;failure<25;++failure) {
            const auto first=run(reference::swoole_typed_array,false,initial,count,keys,flags,rejected,failure);
            const auto second=run(candidate::swoole_typed_array,false,initial,count,keys,flags,rejected,failure);
            if(first!=second){std::cerr<<"construction "<<initial<<':'<<count<<':'<<keys<<':'<<flags<<':'<<rejected<<':'<<failure<<'\n';for(auto &e:first)std::cerr<<"native "<<e<<'\n';for(auto &e:second)std::cerr<<"rust "<<e<<'\n';return 1;}++constructions;
        }
    for(int initial:{1,2})for(int definition:{0,1})for(uint32_t flags=0;flags<4;++flags)for(int failure=-1;failure<12;++failure) {
        const auto first=run(reference::swoole_array_is_typed,true,initial,0,definition,flags,-1,failure);
        const auto second=run(candidate::swoole_array_is_typed,true,initial,0,definition,flags,-1,failure);
        if(first!=second){for(auto &e:first)std::cerr<<"native "<<e<<'\n';for(auto &e:second)std::cerr<<"rust "<<e<<'\n';return 1;}++predicates;
    }
    for(void *p:storage) {::operator delete(p);}
    std::cout<<"{\"actual_construction_effect_cases\":"<<constructions<<",\"actual_predicate_effect_cases\":"<<predicates<<",\"zend_runtime_executed\":false}\n";
}
