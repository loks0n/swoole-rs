// Exact method/reordered-call bodies. Native memory and VM effects are doubles.
#include <cassert>
#include <cstdint>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <functional>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_phphelpers.h"
struct zval {int type,identity;const char *text;size_t length;};
struct CallInfo {zval func,this_;uint8_t op1_type;};
struct zend_execute_data {void **run_time_cache;zval *arguments;int count;};
struct zend_function {int identity;};
struct Interrupted {};
static std::vector<std::string> events;
static std::deque<std::vector<zval>> allocations;
static CallInfo *info;
static zend_execute_data *active;
static int effect,fail_at,change;
static bool function_found;
static zend_function function{55};
static void tick(const std::string &event) {events.push_back(event);if(effect++==fail_at)throw Interrupted{};}
#define IS_VAR 13
#define Z_STRVAL(z) ((z).text)
#define Z_STRLEN(z) ((z).length)
static zval *arguments(zend_execute_data *frame,int first) {assert(first==1);tick("arguments");return frame->arguments;}
#define ZEND_CALL_ARG(frame,first) arguments(frame,first)
static int count(zend_execute_data *frame) {tick("count");return frame->count;}
#define ZEND_CALL_NUM_ARGS(frame) count(frame)
static void *ecalloc(size_t count,size_t size) {assert(size==sizeof(zval));tick("allocate:"+std::to_string(count));allocations.emplace_back(count);return allocations.back().data();}
static void efree(void *pointer) {
    if(pointer==info) {events.push_back("release-info");return;}
    tick("release-arguments");
}
static const char *zend_zval_type_name(const zval *) {return "modeled-value";}
static void zend_throw_error(void *,const char *format,...) {
    char message[1024];va_list args;va_start(args,format);vsnprintf(message,sizeof(message),format,args);va_end(args);tick(std::string("error:")+message);
}
static void zval_ptr_dtor(zval *value) {tick("release-this:"+std::to_string(value->identity));value->identity=-1;}
namespace zend {
static zend_function *get_function(const char *name,size_t length) {tick("lookup:"+std::string(name,length));return function_found?&function:nullptr;}
}
static void zend_call_known_function(zend_function *fn,void *,void *,zval *retval,int count,zval *argv,void *) {
    std::string line="call:"+std::to_string(fn->identity)+":"+std::to_string(count);
    for(int index=0;index<count;++index)line+=':'+std::to_string(argv[index].identity);
    tick(line);retval->identity=77;
    if(change==1)info->op1_type=IS_VAR;
    if(change==2)info->op1_type=0;
    // Stable original CallInfo survives modeled callback reentry; current cache
    // changes independently and original scope cleanup must still clear it.
    active->run_time_cache=reinterpret_cast<void **>(uintptr_t(16));
}
struct ScopeExit {};
template<class F>struct Guard {F fn;~Guard(){fn();}};
template<class F>static Guard<F> operator+(ScopeExit,F fn) {return {fn};}
#define ON_SCOPE_EXIT auto cleanup=ScopeExit{}+[&]()
namespace reference {
#include "reference-invocation.inc"
}
namespace candidate {
#include "candidate-invocation.inc"
}
template<class Method>static std::vector<std::string> run(Method method,const std::string &name,int argc,bool temporary,bool found,int mutation,int failure) {
    events.clear();allocations.clear();effect=0;fail_at=failure;change=mutation;function_found=found;
    CallInfo call_info{{6,0,name.data(),name.size()},{7,41,nullptr,0},uint8_t(temporary?IS_VAR:0)};info=&call_info;
    std::vector<zval> input(size_t(argc)+1);for(int i=0;i<argc;++i)input[size_t(i)]={4,10+i,nullptr,0};
    zend_execute_data frame{reinterpret_cast<void **>(&call_info),input.data(),argc};active=&frame;zval retval{};
    try {method(&frame,&retval);events.push_back("return");}catch(const Interrupted &){events.push_back("interrupted");}
    events.push_back("cache:"+std::to_string(frame.run_time_cache==nullptr));events.push_back("retval:"+std::to_string(retval.identity));events.push_back("this:"+std::to_string(call_info.this_.identity));return events;
}
using Reorder=void (*)(zend_function *,zend_execute_data *,zval *,int);
static std::vector<std::string> reordered(Reorder fn,int argc,int position,int failure) {
    return run([&](zend_execute_data *frame,zval *retval){fn(&function,frame,retval,position);},"reorder",argc,false,true,0,failure);
}
int main() {
    size_t methods=0,reorders=0;
    const std::vector<std::vector<std::string>> names={{"sum","join","jsonEncode",std::string("missing\0tail",12)},
        {"length","lower","htmlSpecialCharsEncode","missing"},{"write","seek","dataSync","missing"}};
    for(uint32_t family=0;family<3;++family)for(const auto &name:names[family])for(int argc=0;argc<5;++argc)
        for(bool temporary:{false,true})for(bool found:{false,true})for(int mutation=0;mutation<3;++mutation)for(int failure=-1;failure<9;++failure) {
            const std::unordered_map<std::string,std::string> *maps[]={&reference::array_methods,&reference::string_methods,&reference::stream_methods};
            const auto before=run([&](zend_execute_data *f,zval *r){reference::call_method(*maps[family],f,r);},name,argc,temporary,found,mutation,failure);
            const auto after=run([&](zend_execute_data *f,zval *r){candidate::call_method(family,f,r);},name,argc,temporary,found,mutation,failure);
            if(before!=after){for(auto &e:before)std::cerr<<"native "<<e<<'\n';for(auto &e:after)std::cerr<<"rust "<<e<<'\n';return 1;}++methods;
        }
    for(int argc=1;argc<10;++argc)for(int position=0;position<argc;++position)for(int failure=-1;failure<7;++failure) {
        const auto before=reordered(reference::call_func_move_first_arg,argc,position,failure);
        const auto after=reordered(candidate::call_func_move_first_arg,argc,position,failure);
        if(before!=after){for(auto &e:before)std::cerr<<"native "<<e<<'\n';for(auto &e:after)std::cerr<<"rust "<<e<<'\n';return 1;}++reorders;
    }
    std::cout<<"{\"actual_method_invocation_effect_cases\":"<<methods<<",\"actual_reordered_invocation_effect_cases\":"<<reorders<<",\"zend_runtime_executed\":false}\n";
}
