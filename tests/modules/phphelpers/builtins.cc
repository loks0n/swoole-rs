// Complete pinned/selected builtin wrappers; native Zend effects are doubles.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum { IS_UNDEF=0,IS_LONG=4,IS_ARRAY=7,IS_REFERENCE=10,HASH_FLAG_TYPED_ARRAY=1<<12 };
struct HashTable;
struct zval { int id,type,number;HashTable *array;zval *reference; };
struct ArrayTypeInfo { int owner;bool check(const HashTable *,const zval *,const zval *) const; };
struct HashTable { uint32_t flags;int identity;ArrayTypeInfo info;std::vector<zval> values; };
struct zend_execute_data { std::vector<zval> args;int count; };
#define INTERNAL_FUNCTION_PARAMETERS zend_execute_data *execute_data,zval *return_value
#define INTERNAL_FUNCTION_PARAM_PASSTHRU execute_data,return_value
#define PHP_FUNCTION(name) void name(INTERNAL_FUNCTION_PARAMETERS)
#define ZEND_CALL_ARG(frame,index) (&(frame)->args[(index)-1])
#define ZEND_CALL_NUM_ARGS(frame) ((frame)->count)
#define ZVAL_DEREF(value) do { if((value)->type==IS_REFERENCE)(value)=(value)->reference; } while(false)
#define Z_TYPE_P(value) ((value)->type)
#define Z_ARRVAL_P(value) ((value)->array)
#define HT_FLAGS(array) ((array)->flags)
static zval uninitialized_zval{0,IS_UNDEF,0,nullptr,nullptr};
#define EG(name) (name)
#define ZEND_HASH_FOREACH_VAL(table,value) for(size_t bucket=0;bucket<(table)->values.size();++bucket) { \
    if((table)->values[bucket].type==IS_UNDEF) { continue; } value=&(table)->values[bucket];
#define ZEND_HASH_FOREACH_END() }
static std::vector<std::string> events;
static HashTable arrays[3],replacement;
static zval *live_array;
static int invalid_value,check_count;
static bool mutate_on_check,handler_copy;
bool ArrayTypeInfo::check(const HashTable *source,const zval *key,const zval *value) const {
    assert(key==&uninitialized_zval);
    events.push_back("check:"+std::to_string(owner)+":"+std::to_string(source->identity)+":"+std::to_string(value->id));
    ++check_count;if(mutate_on_check && check_count==1)live_array->array=&arrays[1];
    if(value->id==invalid_value) { for(auto &array:arrays)array.flags=0;return false; }
    return true;
}
static ArrayTypeInfo *get_type_info(HashTable *array) {
    events.push_back("metadata:"+std::to_string(array->identity));return &array->info;
}
static bool is_typed_array(const zval *array) {
    events.push_back("typed:"+std::to_string(array->array->identity));
    return (array->array->flags&HASH_FLAG_TYPED_ARRAY)!=0;
}
static void original(INTERNAL_FUNCTION_PARAMETERS,const char *name) {
    zval *array=&execute_data->args[0];ZVAL_DEREF(array);
    events.push_back(std::string("original:")+name+":"+std::to_string(array->type==IS_ARRAY ? array->array->identity : 0));
    if(array->type==IS_ARRAY) {
        if(handler_copy)array->array=&arrays[2];
        for(auto &entry:arrays)entry.flags=0;
    }
    return_value->number=execute_data->count+10;
}
static void ori_handler_array_push(INTERNAL_FUNCTION_PARAMETERS) { original(INTERNAL_FUNCTION_PARAM_PASSTHRU,"push"); }
static void ori_handler_array_unshift(INTERNAL_FUNCTION_PARAMETERS) { original(INTERNAL_FUNCTION_PARAM_PASSTHRU,"unshift"); }
static void ori_handler_array_splice(INTERNAL_FUNCTION_PARAMETERS) { original(INTERNAL_FUNCTION_PARAM_PASSTHRU,"splice"); }
namespace reference {
#include "reference-builtins.inc"
}
namespace candidate {
#include "candidate-builtins.inc"
}
template<class Function> static std::vector<std::string> run(
    Function function,int count,int input,bool typed,bool reentry,bool copied,int shape,int invalid) {
    for(int i=0;i<3;++i)arrays[i]={typed ? uint32_t(HASH_FLAG_TYPED_ARRAY) : 0u,i+1,{i+1},{}};
    replacement={0,4,{4},{{100,IS_LONG,1,nullptr,nullptr},{199,IS_UNDEF,0,nullptr,nullptr},
                         {101,IS_LONG,2,nullptr,nullptr},{102,IS_LONG,3,nullptr,nullptr}}};
    if(shape==3)replacement.values.clear();
    if(shape==4)for(auto &value:replacement.values)value.type=IS_UNDEF;
    zval indirect_array{0,input==3 ? IS_LONG : IS_ARRAY,0,&arrays[0],nullptr};
    zval indirect_replacement{30,IS_ARRAY,0,&replacement,nullptr};
    zend_execute_data frame{{},count};
    for(int i=0;i<6;++i)frame.args.push_back({i,IS_LONG,i,nullptr,nullptr});
    frame.args[0]=input==0 ? zval{0,IS_ARRAY,0,&arrays[0],nullptr} :
        ((input==1 || input==3) ? zval{0,IS_REFERENCE,0,nullptr,&indirect_array} : zval{0,IS_LONG,0,nullptr,nullptr});
    frame.args[3]=shape==0 ? zval{3,IS_LONG,3,nullptr,nullptr} :
        (shape==2 ? zval{3,IS_REFERENCE,0,nullptr,&indirect_replacement} : zval{3,IS_ARRAY,0,&replacement,nullptr});
    live_array=(input==1 || input==3) ? &indirect_array : &frame.args[0];
    invalid_value=invalid;check_count=0;mutate_on_check=reentry;handler_copy=copied;
    zval returned{200,IS_LONG,99,nullptr,nullptr};events.clear();function(&frame,&returned);
    events.push_back("checks:"+std::to_string(check_count));
    events.push_back("result:"+std::to_string(returned.number));
    events.push_back("array:"+std::to_string(live_array->type==IS_ARRAY ? live_array->array->identity : 0));
    for(const auto &array:arrays)events.push_back("flags:"+std::to_string(array.identity)+":"+std::to_string(array.flags));
    return events;
}
int main() {
    using Function=void(*)(zend_execute_data *,zval *);
    const Function originals[]={reference::swoole_array_push,reference::swoole_array_unshift,reference::swoole_array_splice};
    const Function selected[]={candidate::swoole_array_push,candidate::swoole_array_unshift,candidate::swoole_array_splice};
    size_t cases=0;
    for(int operation=0;operation<3;++operation)for(int count=1;count<=6;++count)
    for(int input=0;input<4;++input)for(bool typed:{false,true})for(bool reentry:{false,true})
    for(bool copied:{false,true})for(int shape=0;shape<5;++shape)for(int invalid:{-1,1,2,3,4,5,100,101,102}) {
        const auto before=run(originals[operation],count,input,typed,reentry,copied,shape,invalid);
        const auto after=run(selected[operation],count,input,typed,reentry,copied,shape,invalid);
        if(before!=after) {
            std::cerr<<"builtin mismatch "<<operation<<':'<<count<<':'<<input<<':'<<typed<<':'<<reentry<<':'<<copied<<':'<<shape<<':'<<invalid<<'\n';
            for(const auto &event:before)std::cerr<<"native "<<event<<'\n';
            for(const auto &event:after)std::cerr<<"rust "<<event<<'\n';
            return 1;
        }
        ++cases;
    }
    std::cout<<"{\"actual_builtin_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
