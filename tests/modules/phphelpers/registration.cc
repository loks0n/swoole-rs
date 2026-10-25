// Complete stdext MINIT bodies; Zend tables/handlers remain controlled native storage.
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
struct zend_execute_data {};
using user_opcode_handler_t=int (*)(zend_execute_data *);
using zif_handler=void (*)();
static int opcode_handler_method_call(zend_execute_data *){return 1;}
static int opcode_handler_array_assign(zend_execute_data *){return 2;}
static int opcode_handler_array_assign_op(zend_execute_data *){return 3;}
static int opcode_handler_array_unset(zend_execute_data *){return 4;}
static int opcode_handler_foreach_begin(zend_execute_data *){return 5;}
static void original_a(){}static void original_b(){}
static void replacement_swoole_array_push(){}static void replacement_swoole_array_unshift(){}static void replacement_swoole_array_splice(){}
#define ZEND_FN(name) replacement_##name
#define ZEND_STRL(name) name,sizeof(name)-1
#define CG(name) nullptr
#define ZEND_INIT_METHOD_CALL 1
#define ZEND_ASSIGN_DIM 2
#define ZEND_ASSIGN_DIM_OP 3
#define ZEND_UNSET_DIM 4
#define ZEND_FE_RESET_RW 5
static std::vector<std::string> events;
static int effect,fail_at;
static bool observing;
struct Interrupted {};
static void tick(const std::string &event){events.push_back(event);if(effect++==fail_at)throw Interrupted{};}
static int id(zif_handler value){
    if(value==original_a)return 1;
    if(value==original_b)return 2;
    if(value==replacement_swoole_array_push)return 3;
    if(value==replacement_swoole_array_unshift)return 4;
    if(value==replacement_swoole_array_splice)return 5;
    assert(!value);return 0;
}
struct Handler {
    zif_handler value=nullptr;
    size_t slot=0;
    operator zif_handler()const {if(observing)tick("capture:"+std::to_string(slot)+":"+std::to_string(id(value)));return value;}
    Handler &operator=(zif_handler next){if(observing)tick("replace:"+std::to_string(slot)+":"+std::to_string(id(next)));value=next;return *this;}
};
struct zend_function {struct {Handler handler;} internal_function;};
static std::array<zend_function,6> functions;
static std::array<int,5> hooks;
static const char *names[]={"swoole_call_array_method","swoole_call_string_method","swoole_call_stream_method","array_push","array_unshift","array_splice"};
static void zend_set_user_opcode_handler(uint8_t opcode,user_opcode_handler_t handler){tick("opcode:"+std::to_string(opcode)+":"+std::to_string(handler(nullptr)));hooks.at(opcode-1)=handler(nullptr);}
namespace zend {
static zend_function *get_function(void *,const char *name,size_t length){
    tick("lookup:"+std::string(name,length));assert(name[length]=='\0');
    for(size_t i=0;i<6;++i)if(std::string(name,length)==names[i])return &functions[i];
    assert(false);return nullptr;
}
}
namespace reference {
#include "reference-registration.inc"
}
namespace candidate {
#include "candidate-registration.inc"
}
using Init=void (*)(int);
static std::vector<std::string> run(Init init,zend_function ***cache,zif_handler **previous,int failure,bool warm,bool alternate){
    observing=false;events.clear();hooks.fill(0);
    for(size_t i=0;i<6;++i){functions[i].internal_function.handler.slot=i;functions[i].internal_function.handler.value=alternate?original_b:original_a;*cache[i]=nullptr;}
    for(size_t i=0;i<3;++i)*previous[i]=nullptr;
    fail_at=-1;effect=0;
    if(warm){observing=true;init(17);observing=false;}
    events.clear();effect=0;fail_at=failure;observing=true;
    try{init(17);events.push_back("initialized");}catch(const Interrupted &){events.push_back("interrupted");}
    observing=false;
    for(size_t i=0;i<6;++i)events.push_back("function:"+std::to_string(i)+":"+std::to_string(*cache[i]==&functions[i])+":"+std::to_string(id(functions[i].internal_function.handler.value)));
    for(size_t i=0;i<3;++i)events.push_back("previous:"+std::to_string(i)+":"+std::to_string(id(*previous[i])));
    for(int hook:hooks)events.push_back("hook:"+std::to_string(hook));
    return events;
}
#define CACHES(ns) &ns::fn_swoole_call_array_method,&ns::fn_swoole_call_string_method,&ns::fn_swoole_call_stream_method,&ns::fn_array_push,&ns::fn_array_unshift,&ns::fn_array_splice
#define PREVIOUS(ns) &ns::ori_handler_array_push,&ns::ori_handler_array_unshift,&ns::ori_handler_array_splice
int main(){
    zend_function **before_cache[]={CACHES(reference)},**after_cache[]={CACHES(candidate)};
    zif_handler *before_previous[]={PREVIOUS(reference)},*after_previous[]={PREVIOUS(candidate)};
    size_t cases=0;
    for(bool alternate:{false,true})for(bool warm:{false,true})for(int failure=-1;failure<19;++failure){
        auto before=run(reference::php_swoole_stdext_minit,before_cache,before_previous,failure,warm,alternate);
        auto after=run(candidate::php_swoole_stdext_minit,after_cache,after_previous,failure,warm,alternate);
        if(before!=after){for(auto &event:before)std::cerr<<"native "<<event<<'\n';for(auto &event:after)std::cerr<<"rust "<<event<<'\n';return 1;}++cases;
    }
    std::cout<<"{\"actual_registration_effect_cases\":"<<cases<<",\"opcode_handlers\":5,\"function_lookups\":6,\"handler_replacements\":3,\"zend_runtime_executed\":false}\n";
}
