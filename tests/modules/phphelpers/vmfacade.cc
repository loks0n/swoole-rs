// Complete VM facade bodies; storage and Zend VM effects are controlled doubles.
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum { IS_UNDEF=0,IS_LONG=4,IS_ARRAY=7,IS_REFERENCE=10,
       IS_CONST=11,IS_VAR=12,IS_CV=13,IS_TMP_VAR=14,IS_UNUSED=15,
       HASH_FLAG_TYPED_ARRAY=1,ZEND_USER_OPCODE_DISPATCH=20,ZEND_USER_OPCODE_CONTINUE=21 };
struct zend_op { struct Node {int var;}op1,op2,result;int op1_type,op2_type; };
struct zval;
struct zend_array { uint32_t flags;bool list; };
struct zval { int type;zend_array *array;zval *ref;uint32_t iterator;int identity; };
struct zend_execute_data {const zend_op *opline;zval operand,key,value,result;};
struct Interrupted {};
static std::vector<std::string> events;
static int effect,fail_at;
static bool valid,refresh_key;
static zval uninitialized_zval;
static void tick(const std::string &name) {events.push_back(name);if(effect++==fail_at)throw Interrupted{};}
#define EXECUTE_DATA_DC , zend_execute_data *execute_data
#define EXECUTE_DATA_CC , execute_data
#define EX(field) (execute_data->field)
#define EG(field) field
#define UNEXPECTED(value) (value)
#define ZVAL_IS_REF(z) ((z)->type==IS_REFERENCE)
#define Z_REFVAL_P(z) ((z)->ref)
#define ZVAL_IS_ARRAY(z) ((z)->type==IS_ARRAY)
#define ZVAL_DEREF(z) do {if(ZVAL_IS_REF(z))z=Z_REFVAL_P(z);} while(0)
#define Z_ARRVAL_P(z) ((z)->array)
#define HT_FLAGS(ht) ((ht)->flags)
#define Z_FE_ITER_P(z) ((z)->iterator)
static zval *fetch_variable(int variable,zend_execute_data *frame) {tick("fetch-variable:"+std::to_string(variable));return &frame->operand;}
static zval *fetch_temporary(int variable,zend_execute_data *frame) {tick("fetch-temporary:"+std::to_string(variable));return &frame->operand;}
#define _get_zval_ptr_ptr_var fetch_variable
#define _get_zval_ptr_tmp fetch_temporary
static zval *constant(int variable,zend_execute_data *frame) {tick("constant:"+std::to_string(variable));return variable==0?&frame->operand:&frame->key;}
#define RT_CONSTANT(opline,node) constant((node).var,execute_data)
static zval *variable(int index,zend_execute_data *frame) {tick("variable:"+std::to_string(index));return index==2?&frame->result:&frame->key;}
#define EX_VAR(index) variable(index,execute_data)
static zval *fetch_value(int type,int variable,zend_execute_data *frame) {tick("value:"+std::to_string(type)+":"+std::to_string(variable));
    if(refresh_key) {auto *instruction=const_cast<zend_op *>(frame->opline);instruction->op2_type=instruction->op2_type==IS_CONST?IS_UNUSED:instruction->op2_type==IS_UNUSED?IS_VAR:IS_CONST;}
    return &frame->value;}
#define get_op_data_zval_ptr_r(type,node) fetch_value(type,(node).var,execute_data)
static void free_operand(int type,int variable) {tick("free:"+std::to_string(type)+":"+std::to_string(variable));}
#define FREE_OP(type,variable) free_operand(type,variable)
static void undef(zval *z) {tick("undef");z->type=IS_UNDEF;}
#define ZVAL_UNDEF(z) undef(z)
static void zend_throw_error(void *,const char *message) {tick(std::string("error:")+message);}
struct ArrayTypeInfo {
    const zend_array *array;
    bool is_list()const {tick("list");return array->list;}
    bool check(const zend_array *,const zval *key,const zval *value)const {
        tick("check:"+std::to_string(key->identity)+":"+std::to_string(value->identity));return valid;
    }
};
static ArrayTypeInfo info;
static ArrayTypeInfo *get_type_info(const zend_array *array) {tick("metadata");info.array=array;return &info;}
using ArrayFn=std::function<void(const zend_op *,zval *,const zval *,zval *,zend_execute_data *)>;
namespace reference {
#include "reference-vmfacade.inc"
}
namespace candidate {
#include "candidate-vmfacade.inc"
}
using Facade=int (*)(zend_execute_data *);
using Assignment=int (*)(zend_execute_data *,const ArrayFn &);
static std::vector<std::string> run(Facade facade,Assignment assignment,int operation,int shape,bool typed,bool list,int op1,int op2,bool check,int failure) {
    zend_array array{typed?uint32_t(HASH_FLAG_TYPED_ARRAY):0,list};
    zval target{shape%2?IS_ARRAY:IS_LONG,&array,nullptr,0,8};
    zend_op opcodes[3]{};opcodes[0].op1_type=op1;opcodes[0].op2_type=op2;
    opcodes[0].op1.var=0;opcodes[0].op2.var=1;opcodes[0].result.var=2;
    opcodes[1].op1_type=IS_VAR;opcodes[1].op1.var=3;
    zend_execute_data frame{opcodes,shape>=2?zval{IS_REFERENCE,nullptr,&target,0,9}:target,
                            {IS_LONG,nullptr,nullptr,0,11},{IS_LONG,nullptr,nullptr,0,12},{IS_LONG,nullptr,nullptr,99,13}};
    uninitialized_zval={IS_UNDEF,nullptr,nullptr,0,17};valid=check;fail_at=failure;effect=0;events.clear();
    ArrayFn invoke=[&](const zend_op *instruction,zval *container,const zval *key,zval *input,zend_execute_data *data) {
        assert(instruction==opcodes&&data==&frame);tick("invoke:"+std::to_string(container->identity)+":"+std::to_string(key->identity)+":"+std::to_string(input->identity));
        // The caller advances the current native opline after callback return.
        data->opline=opcodes+1;data->result.identity=25;
    };
    try {int result=operation==0?assignment(&frame,invoke):facade(&frame);events.push_back("return:"+std::to_string(result));}
    catch(const Interrupted &) {events.push_back("interrupted");}
    events.push_back("opline:"+std::to_string(frame.opline-opcodes));
    events.push_back("result:"+std::to_string(frame.result.type)+":"+std::to_string(frame.result.iterator)+":"+std::to_string(frame.result.identity));
    return events;
}
int main() {
    size_t cases=0;
    for(int operation=0;operation<3;++operation)for(int shape=0;shape<4;++shape)
        for(bool fresh:{false,true})for(bool typed:{false,true})for(bool list:{false,true})for(int op1:{IS_VAR,IS_CV,IS_CONST,IS_TMP_VAR,IS_UNUSED})
            for(int op2:{IS_CONST,IS_VAR,IS_UNUSED})for(bool check:{false,true})for(int failure=-1;failure<13;++failure) {
                refresh_key=fresh;Facade before=operation==1?reference::opcode_handler_foreach_begin:reference::opcode_handler_array_unset;
                Facade after=operation==1?candidate::opcode_handler_foreach_begin:candidate::opcode_handler_array_unset;
                const auto first=run(before,reference::opcode_handler_array,operation,shape,typed,list,op1,op2,check,failure);
                const auto second=run(after,candidate::opcode_handler_array,operation,shape,typed,list,op1,op2,check,failure);
                if(first!=second){std::cerr<<"facade mismatch "<<operation<<':'<<shape<<':'<<typed<<':'<<list<<':'<<op1<<':'<<op2<<':'<<check<<':'<<failure<<'\n';for(auto &e:first)std::cerr<<"native "<<e<<'\n';for(auto &e:second)std::cerr<<"rust "<<e<<'\n';return 1;}++cases;
            }
    std::cout<<"{\"actual_vm_facade_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
