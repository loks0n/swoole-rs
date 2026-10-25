// Complete wrapper body; PCRE cache/matching and Zend storage are controlled doubles.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
using zend_long=int64_t;
struct zend_string {std::string value;};
struct pcre_cache_entry {int references;};
struct zval {int tag;};
struct Input {zend_string subject,regex;zend_long flags,start_offset;int argc;bool compiled;};
static Input input;
static pcre_cache_entry cached;
static std::vector<std::string> events;
static int effect,fail_at;
struct Interrupted {};
static void tick(const std::string &event){events.push_back(event);if(effect++==fail_at)throw Interrupted{};}
#define INTERNAL_FUNCTION_PARAMETERS zval *return_value
#define ZEND_PARSE_PARAMETERS_START(min,max) {size_t parameter=0;assert(input.argc>=min&&input.argc<=max);
#define Z_PARAM_STR(value) value=parameter++==0?&input.subject:&input.regex;
#define Z_PARAM_OPTIONAL
#define Z_PARAM_LONG(value) if(parameter++<static_cast<size_t>(input.argc))value=input.value;
#define ZEND_PARSE_PARAMETERS_END() }
#define ZEND_NUM_ARGS() input.argc
#define RETURN_FALSE do{return_value->tag=0;events.push_back("return-false");return;}while(0)
static pcre_cache_entry *pcre_get_compiled_regex_cache(zend_string *regex){
    assert(regex==&input.regex);tick("compile:"+regex->value);return input.compiled?&cached:nullptr;
}
static void php_pcre_pce_incref(pcre_cache_entry *pce){assert(pce==&cached);tick("incref:"+std::to_string(pce->references));++pce->references;}
static void php_pcre_pce_decref(pcre_cache_entry *pce){assert(pce==&cached);tick("decref:"+std::to_string(pce->references));--pce->references;}
#if PHP_VERSION_ID >= 80400
static void php_pcre_match_impl(pcre_cache_entry *pce,zend_string *subject,zval *count,zval *result,bool global,zend_long flags,zend_long offset){
#else
static void php_pcre_match_impl(pcre_cache_entry *pce,zend_string *subject,zval *count,zval *result,int global,bool use_flags,zend_long flags,zend_long offset){
#endif
    assert(pce==&cached&&pce->references==1&&subject==&input.subject&&count->tag==0);
    tick("match:"+subject->value+":"+std::to_string(global)+":"+std::to_string(flags)+":"+std::to_string(offset)
#if PHP_VERSION_ID < 80400
         +":use-flags:"+std::to_string(use_flags)
#endif
    );
    count->tag=3;result->tag=72;
}
namespace reference {
#include "reference-regex.inc"
}
namespace candidate {
#include "candidate-regex.inc"
}
using Wrapper=void (*)(zval *,int);
static std::vector<std::string> run(Wrapper wrapper,int global,int failure){
    events.clear();cached.references=0;effect=0;fail_at=failure;zval result{-1};
    try{wrapper(&result,global);events.push_back("returned");}catch(const Interrupted &){events.push_back("interrupted");}
    events.push_back("references:"+std::to_string(cached.references));events.push_back("result:"+std::to_string(result.tag));return events;
}
int main(){
    size_t cases=0;
    for(bool compiled:{false,true})for(int argc:{2,3,4})for(zend_long flags:{-7,0,64})for(zend_long offset:{-2,0,3})for(int global:{0,1})for(int failure=-1;failure<5;++failure){
        input={{std::string("a\0b",3)},{"literal-policy-fixture"},flags,offset,argc,compiled};
        const auto before=run(reference::php_do_pcre_match,global,failure),after=run(candidate::php_do_pcre_match,global,failure);
        if(before!=after){for(const auto &event:before)std::cerr<<"native "<<event<<'\n';for(const auto &event:after)std::cerr<<"rust "<<event<<'\n';return 1;}++cases;
    }
    std::cout<<"{\"actual_regex_wrapper_effect_cases\":"<<cases<<",\"php_version_id\":"<<PHP_VERSION_ID<<",\"pcre_library_executed\":false,\"zend_runtime_executed\":false}\n";
}
