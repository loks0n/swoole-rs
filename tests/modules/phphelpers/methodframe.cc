// Complete method opcode frame construction; VM/storage effects are doubles.
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum { IS_UNDEF=0,IS_NULL=1,IS_FALSE=2,IS_TRUE=3,IS_LONG=4,IS_DOUBLE=5,
       IS_STRING=6,IS_ARRAY=7,IS_OBJECT=8,IS_RESOURCE=9,IS_REFERENCE=10,
       IS_CONST=11,IS_UNUSED=12,IS_VAR=13,ZEND_CALL_NESTED_FUNCTION=14,
       ZEND_USER_OPCODE_DISPATCH=20,ZEND_USER_OPCODE_CONTINUE=21 };
struct zval {int type,identity;zval *reference;};
struct CallInfo {zval func,this_;uint8_t op1_type;};
struct zend_function {int identity;};
struct zend_op {struct Node {int var;}op1,op2;int op1_type;uint32_t extended_value;};
struct zend_execute_data {const zend_op *opline;void **run_time_cache;zend_execute_data *prev_execute_data,*call;zval object;};
struct Interrupted {};
static std::vector<std::string> events;
static int effect,fail_at;
static CallInfo allocation;
static zend_execute_data created,refreshed_previous;
static zend_execute_data *active;
static bool refresh_parent;
static zend_function array_fn{1},string_fn{2},stream_fn{3};
static zend_function *fn_swoole_call_array_method=&array_fn,*fn_swoole_call_string_method=&string_fn,*fn_swoole_call_stream_method=&stream_fn;
static void tick(const std::string &event) {events.push_back(event);if(effect++==fail_at)throw Interrupted{};}
#define EX(field) (execute_data->field)
#define UNEXPECTED(value) (value)
#define Z_TYPE_P(z) ((z)->type)
#define Z_REFVAL_P(z) ((z)->reference)
static zval function_name{IS_STRING,99,nullptr};
static zval *constant(int variable,zend_execute_data *frame) {tick("constant:"+std::to_string(variable));return variable==0?&frame->object:&function_name;}
#define RT_CONSTANT(opline,node) constant((node).var,execute_data)
static zval *variable(int index,zend_execute_data *frame) {tick("variable:"+std::to_string(index));return &frame->object;}
#define EX_VAR(index) variable(index,execute_data)
static void *emalloc(size_t size) {tick("allocate:"+std::to_string(size));allocation={};return &allocation;}
static zend_execute_data *zend_vm_stack_push_call_frame(int kind,zend_function *fn,uint32_t count,zval *object) {
    tick("push:"+std::to_string(kind)+":"+std::to_string(fn->identity)+":"+std::to_string(count)+":"+std::to_string(object->identity));created={};if(refresh_parent)active->call=&refreshed_previous;return &created;
}
namespace reference {
#include "reference-methodframe.inc"
}
namespace candidate {
#include "candidate-methodframe.inc"
}
using Method=int (*)(zend_execute_data *);
static std::vector<std::string> run(Method method,int operand,int kind,bool reference,int failure) {
    zend_op opcodes[2]{};opcodes[0].op1.var=0;opcodes[0].op2.var=1;opcodes[0].op1_type=operand;opcodes[0].extended_value=7;
    zval target{kind,42,nullptr};zend_execute_data previous{};
    zend_execute_data frame{opcodes,nullptr,nullptr,&previous,reference?zval{IS_REFERENCE,41,&target}:target};
    active=&frame;effect=0;fail_at=failure;events.clear();allocation={};created={};
    try {events.push_back("return:"+std::to_string(method(&frame)));}
    catch(const Interrupted &) {events.push_back("interrupted");}
    events.push_back("opline:"+std::to_string(frame.opline-opcodes));
    events.push_back("call:"+std::to_string(frame.call==&created));
    events.push_back("cache:"+std::to_string(created.run_time_cache==reinterpret_cast<void **>(&allocation)));
    events.push_back("previous:"+std::to_string(created.prev_execute_data==(refresh_parent?&refreshed_previous:&previous)));
    events.push_back("info:"+std::to_string(allocation.func.identity)+":"+std::to_string(allocation.this_.identity)+":"+std::to_string(allocation.op1_type));return events;
}
int main() {
    size_t cases=0;
    for(int operand:{IS_CONST,IS_UNUSED,IS_VAR})for(int kind:{IS_UNDEF,IS_NULL,IS_FALSE,IS_TRUE,IS_LONG,IS_DOUBLE,IS_STRING,IS_ARRAY,IS_OBJECT,IS_RESOURCE})
        for(bool reference:{false,true})for(bool fresh:{false,true})for(int failure=-1;failure<7;++failure) {
            refresh_parent=fresh;const auto first=run(reference::opcode_handler_method_call,operand,kind,reference,failure);
            const auto second=run(candidate::opcode_handler_method_call,operand,kind,reference,failure);
            if(first!=second){for(auto &e:first)std::cerr<<"native "<<e<<'\n';for(auto &e:second)std::cerr<<"rust "<<e<<'\n';return 1;}++cases;
        }
    std::cout<<"{\"actual_method_frame_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
