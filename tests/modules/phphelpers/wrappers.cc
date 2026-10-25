// Eleven complete generated public wrappers; native lookup/cache/call doubles.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
struct zend_execute_data {int argc;};
struct zval {int marker;};
struct zend_function {const char *name;};
#define PHP_FUNCTION(name) void name(zend_execute_data *execute_data,zval *return_value)
#define CG(name) nullptr
#define ZEND_STRL(name) name,sizeof(name)-1
static zend_function functions[]={{"array_search"},{"in_array"},{"implode"},{"array_key_exists"},{"array_map"},{"str_replace"},{"str_ireplace"},{"explode"},{"hash"}};
static std::vector<std::string> events;
static int effect,fail_at;
struct Interrupted {};
static void tick(const std::string &event){events.push_back(event);if(effect++==fail_at)throw Interrupted{};}
namespace zend {
static zend_function *get_function(void *,const char *name,size_t length){
    tick("lookup:"+std::string(name,length));assert(name[length]=='\0');
    for(auto &fn:functions)if(std::string(name,length)==fn.name)return &fn;
    assert(false);return nullptr;
}
}
static void call_func_move_first_arg(zend_function *fn,zend_execute_data *data,zval *result,int position){
    assert(fn);tick("call:"+std::string(fn->name)+":"+std::to_string(data->argc)+":"+std::to_string(position));result->marker=11;
}
namespace reference {
#include "reference-wrappers.inc"
}
#undef SW_CREATE_PHP_FUNCTION_WRAPPER
static size_t binding_queries;
static uint8_t observed_wrapper(uint32_t index,SwrPhpWrapper *output){
    ++binding_queries;return swr_v1_phphelpers_wrapper(index,output);
}
#define swr_v1_phphelpers_wrapper observed_wrapper
namespace candidate {
#include "candidate-wrappers.inc"
}

#undef swr_v1_phphelpers_wrapper
using Wrapper=void (*)(zend_execute_data *,zval *);
#define WRAPPERS(ns) ns::swoole_array_search,ns::swoole_array_contains,ns::swoole_array_join,ns::swoole_array_key_exists,ns::swoole_array_map,ns::swoole_array_replace_str,ns::swoole_array_ireplace_str,ns::swoole_str_split,ns::swoole_hash,ns::swoole_str_replace,ns::swoole_str_ireplace
static std::vector<std::string> run(Wrapper wrapper,int argc,int failure){
    events.clear();effect=0;fail_at=failure;zend_execute_data data{argc};zval result{-1};
    try{wrapper(&data,&result);events.push_back("returned");}catch(const Interrupted &){events.push_back("interrupted");}
    events.push_back("result:"+std::to_string(result.marker));return events;
}
int main(){
    Wrapper before[]={WRAPPERS(reference)},after[]={WRAPPERS(candidate)};
    size_t cases=0;
    for(size_t index=0;index<11;++index)for(int failure:{0,1,-1,0,-1}){
        const int argc=(index==5||index==6||index==9||index==10)?3:2;
        const auto native=run(before[index],argc,failure),selected=run(after[index],argc,failure);
        if(native!=selected){for(const auto &event:native)std::cerr<<"native "<<event<<'\n';for(const auto &event:selected)std::cerr<<"rust "<<event<<'\n';return 1;}++cases;
    }
    assert(binding_queries==22);
    std::cout<<"{\"rust_binding_queries\":"<<binding_queries<<",\"complete_public_wrappers\":11,\"actual_wrapper_cache_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
