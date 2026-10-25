// Exact mutation bodies; Zend allocation/VM/HashTable operations are native doubles.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phphelpers.h"
enum { IS_UNDEF=0,IS_NULL=1,IS_FALSE=2,IS_TRUE=3,IS_LONG=4,IS_DOUBLE=5,
       IS_STRING=6,IS_ARRAY=7,IS_OBJECT=8,IS_RESOURCE=9,IS_REFERENCE=10,
       IS_CONST=11,IS_VAR=12,ZEND_CONCAT=13 };
struct ArrayTypeInfo {
    uint8_t kind;
    bool value_is_string() const { return kind==IS_STRING; }
    bool value_is_numeric() const { return kind==IS_LONG || kind==IS_DOUBLE; }
    uint8_t get_type_of_value() const { return kind; }
};
struct HashTable { ArrayTypeInfo info; int identity; };
struct zend_reference;
struct zval { uint8_t type; int number; HashTable *array; zend_reference *reference; };
struct zend_reference { zval value; bool typed; };
struct zend_op { struct Node { int var; } op1,op2,result; int op1_type,op2_type; uint32_t extended_value; bool used; };
struct zend_execute_data { zval result; };
struct Configuration { bool cow,null_key,constant,found,assigned,used,variable,inserted,reference,typed; };
static Configuration config;
static std::vector<std::string> events;
static HashTable old_array,new_array;
static zval slot;
static zend_reference referenced;
#define EXECUTE_DATA_DC , zend_execute_data *execute_data
#define EXECUTE_DATA_CC , execute_data
#define OPLINE_CC , opline
#define EX_VAR(var) (&execute_data->result)
#define EX_USES_STRICT_TYPES() false
#define Z_ARRVAL_P(z) ((z)->array)
#define ZVAL_IS_NULL(z) ((z)->type==IS_NULL)
#define Z_ISREF_P(z) ((z)->type==IS_REFERENCE)
#define Z_REF_P(z) ((z)->reference)
#define Z_REFVAL_P(z) (&(z)->reference->value)
#define ZEND_REF_HAS_TYPE_SOURCES(ref) ((ref)->typed)
#define UNEXPECTED(value) (value)
#define RETURN_VALUE_USED(opline) ((opline)->used)
static void debug_val(const char *tag,int type,zval *value) { events.push_back(std::string("debug:")+tag+":"+std::to_string(type)+":"+std::to_string(value->number)); }
static void separate(zval *container) { events.push_back("separate");if(config.cow)container->array=&new_array; }
#define SEPARATE_ARRAY(container) separate(container)
static void copy_array_type_info(zval *container,HashTable *source) {
    events.push_back("copy-metadata");container->array->info=source->info;
}
static ArrayTypeInfo *get_type_info(HashTable *array) { return &array->info; }
static void free_op(int type,int variable) { events.push_back("free:"+std::to_string(type)+":"+std::to_string(variable)); }
#define FREE_OP(type,var) free_op(type,var)
static void set_null(zval *value) { events.push_back("null");value->type=IS_NULL;value->number=0; }
#define ZVAL_NULL(value) set_null(value)
static void copy(zval *destination,const zval *source) { events.push_back("copy-result");*destination=*source; }
#define ZVAL_COPY(destination,source) copy(destination,source)
static void addref(zval *) { events.push_back("addref"); }
#define Z_TRY_ADDREF_P(value) addref(value)
static void zend_cannot_add_element() { events.push_back("next-index-error"); }
static zval *zend_hash_next_index_insert(HashTable *,zval *value) {
    events.push_back("insert");if(!config.inserted)return nullptr;slot=*value;return &slot;
}
static zval *fetch(const char *operation) { events.push_back(operation);return config.found ? &slot : nullptr; }
static zval *zend_fetch_dimension_address_inner_W_CONST(HashTable *,const zval *,zend_execute_data *) { return fetch("write-constant"); }
static zval *zend_fetch_dimension_address_inner_W(HashTable *,const zval *,zend_execute_data *) { return fetch("write-variable"); }
static zval *zend_fetch_dimension_address_inner_RW_CONST(HashTable *,const zval *,zend_execute_data *) { return fetch("readwrite-constant"); }
static zval *zend_fetch_dimension_address_inner_RW(HashTable *,const zval *,zend_execute_data *) { return fetch("readwrite-variable"); }
static zval *zend_assign_to_variable(zval *destination,zval *value,int type,bool strict) {
    assert(!strict);events.push_back("assign:"+std::to_string(type));
    if(!config.assigned)return nullptr;
    *destination=*value;return destination;
}
static void zend_binary_assign_op_typed_ref(zend_reference *ref,zval *value,const zend_op *,zend_execute_data *) {
    events.push_back("typed-reference-op");ref->value.number+=value->number;
}
static void zend_binary_op(zval *destination,zval *left,zval *right,const zend_op *) {
    events.push_back("binary-op");destination->number=left->number+right->number;
}
static void zend_type_error(const char *message) { events.push_back(std::string("type-error:")+message); }
namespace reference {
#include "reference-mutation.inc"
}
namespace candidate {
#include "candidate-mutation.inc"
}
template<class Function> static std::vector<std::string> run(Function function,uint16_t flags,uint8_t kind,bool concat) {
    config={bool(flags&1),bool(flags&2),bool(flags&4),bool(flags&8),bool(flags&16),
            bool(flags&32),bool(flags&64),bool(flags&128),bool(flags&256),bool(flags&512)};
    old_array={{kind},1};new_array={{IS_OBJECT},2};
    referenced={{IS_LONG,11,nullptr,nullptr},config.typed};
    slot={config.reference ? uint8_t(IS_REFERENCE) : uint8_t(IS_LONG),7,nullptr,&referenced};
    zval container{IS_ARRAY,0,&old_array,nullptr};
    zval key{config.null_key ? uint8_t(IS_NULL) : uint8_t(IS_LONG),0,nullptr,nullptr};
    zval value{IS_LONG,5,nullptr,nullptr};
    zend_execute_data frame{{IS_UNDEF,99,nullptr,nullptr}};
    zend_op instructions[2]{};
    instructions[0].op2_type=config.constant ? IS_CONST : IS_VAR;
    instructions[0].extended_value=concat ? ZEND_CONCAT : 0;
    instructions[0].used=config.used;
    instructions[1].op1_type=config.variable ? IS_VAR : IS_CONST;
    instructions[1].op1.var=17;
    events.clear();function(instructions,&container,&key,&value,&frame);
    events.push_back("result:"+std::to_string(frame.result.type)+":"+std::to_string(frame.result.number));
    events.push_back("slot:"+std::to_string(slot.type)+":"+std::to_string(slot.number));
    events.push_back("reference:"+std::to_string(referenced.value.number));
    events.push_back("array:"+std::to_string(container.array->identity));return events;
}
int main() {
    size_t cases=0;
    for(uint16_t flags=0;flags<1024;++flags)for(uint8_t kind:{IS_LONG,IS_DOUBLE,IS_STRING,IS_OBJECT})for(bool concat:{false,true}) {
        for(bool operation:{false,true}) {
            const auto before=run(operation ? reference::array_op : reference::array_add_or_update,flags,kind,concat);
            const auto after=run(operation ? candidate::array_op : candidate::array_add_or_update,flags,kind,concat);
            if(before!=after) {
                std::cerr<<"mutation mismatch "<<flags<<':'<<unsigned(kind)<<':'<<concat<<':'<<operation<<'\n';
                for(const auto &event:before)std::cerr<<"native "<<event<<'\n';
                for(const auto &event:after)std::cerr<<"rust "<<event<<'\n';
                return 1;
            }
            ++cases;
        }
    }
    std::cout<<"{\"actual_mutation_effect_cases\":"<<cases<<",\"zend_runtime_executed\":false}\n";
}
