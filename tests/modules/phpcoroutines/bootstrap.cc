// Exact three MINIT bodies, inert class/handler/constant/opcode records only. No Zend/callback execution.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = long;
std::vector<std::string> trace;
struct Fact {
    bool value; const char *label;
    operator bool() const { trace.push_back(label); return value; }
};
struct Globals { Fact use_shortname{false,"short-flag"}, cli{false,"cli-flag"}; void *in_autoload; } globals;
#define SWOOLE_G(name) globals.name
struct zend_function_entry { int tag; };
struct zend_class_entry { const char *name; size_t length; unsigned ce_flags; };
struct zend_object_handlers { unsigned tag; };
zend_class_entry parent_array_iterator{"ArrayIterator",13,0}, parent_array_object{"ArrayObject",11,0};
zend_class_entry parent_exception{"Exception",9,0}, parent_swoole_exception{"SwooleException",15,0};
zend_class_entry *spl_ce_ArrayIterator=&parent_array_iterator, *spl_ce_ArrayObject=&parent_array_object;
zend_class_entry *zend_ce_exception=&parent_exception, *swoole_exception_ce=&parent_swoole_exception;
zend_object_handlers standard_handlers{101}, swoole_exception_handlers{202};
#define DECLARE(module) zend_class_entry *module##_ce; zend_object_handlers module##_handlers{};
DECLARE(swoole_coroutine_util) DECLARE(swoole_coroutine_iterator) DECLARE(swoole_coroutine_context)
DECLARE(swoole_exit_exception) DECLARE(swoole_coroutine_canceled_exception) DECLARE(swoole_coroutine_timeout_exception)
DECLARE(swoole_coroutine_scheduler) DECLARE(swoole_coroutine_system)
zend_function_entry swoole_coroutine_methods[1]{{1}}, swoole_exit_exception_methods[1]{{2}};
zend_function_entry swoole_coroutine_scheduler_methods[1]{{3}}, swoole_coroutine_system_methods[1]{{4}};
#ifdef SWOOLE_RS_PHPCOROUTINES
// Projection is an inert Native effect here. Exact real projector/table/handler
// metadata is qualified separately by methods.py; no Zend methods execute.
struct PHPCoroutineMethodBinding { int tag; };
const PHPCoroutineMethodBinding swoole_coroutine_methods_bindings[]{{1}}, swoole_exit_exception_methods_bindings[]{{2}};
const PHPCoroutineMethodBinding swoole_coroutine_scheduler_methods_bindings[]{{3}}, swoole_coroutine_system_methods_bindings[]{{4}};
void php_coroutine_project_methods(uint32_t kind, const PHPCoroutineMethodBinding *binding, zend_function_entry *projection) {
    assert(binding->tag == int(kind + 1));
    assert(projection->tag == binding->tag);
}
#endif
unsigned registrations, mode;
zend_class_entry classes[16];
#define INIT_CLASS_ENTRY_EX(entry, name, length, methods) init_entry(entry,name,length,methods)
#define INIT_CLASS_ENTRY(entry, name, methods) INIT_CLASS_ENTRY_EX(entry,name,sizeof(name)-1,methods)
void init_entry(zend_class_entry &entry, const char *name, size_t length, const zend_function_entry *methods) {
    assert(std::strlen(name)==length); entry={name,length,0};
    trace.push_back("init:"+std::string(name,length)+":"+std::to_string(methods ? methods->tag : 0));
}
zend_class_entry *zend_register_internal_class_ex(zend_class_entry *entry, zend_class_entry *parent) {
    trace.push_back("register:"+std::string(entry->name,entry->length)+":"+(parent ? parent->name : "none"));
    assert(registrations<16); classes[registrations]=*entry;
    if (mode==2) globals.use_shortname.value=!globals.use_shortname.value;
    return &classes[registrations++];
}
void sw_zend_register_class_alias(const char *name, size_t length, zend_class_entry *entry) {
    assert(std::strlen(name)==length);
    trace.push_back("alias:"+std::string(name,length)+":"+entry->name);
    if (mode==3) globals.use_shortname.value=!globals.use_shortname.value;
}
zend_object_handlers *zend_get_std_object_handlers() { trace.push_back("std-handlers"); return &standard_handlers; }
void *record_copy(void *dest, const void *src, size_t size) {
    assert(size==sizeof(zend_object_handlers));
    trace.push_back("copy:"+std::to_string(static_cast<const zend_object_handlers *>(src)->tag));
    return std::memcpy(dest,src,size);
}
void *record_clear(void *dest, int value, size_t length) { trace.push_back("clear-internal"); return std::memset(dest,value,length); }
#define memcpy record_copy
#define memset record_clear
#define SW_CLASS_ALIAS_SHORT_NAME(alias, module) do { if (SWOOLE_G(use_shortname)) sw_zend_register_class_alias(alias,sizeof(alias)-1,module##_ce); } while(false)
// This preserves the pinned macro's short-null admission and effect order.
#define SW_INIT_CLASS_ENTRY_BASE(module, name, alias, methods, parent) do { \
    zend_class_entry entry{}; INIT_CLASS_ENTRY(entry,name,methods); \
    module##_ce=zend_register_internal_class_ex(&entry,parent); \
    const char *short_name_native = alias; if (short_name_native) SW_CLASS_ALIAS_SHORT_NAME(alias,module); } while(false)
#define SW_INIT_CLASS_ENTRY(module,name,alias,methods) SW_INIT_CLASS_ENTRY_BASE(module,name,alias,methods,nullptr); memcpy(&module##_handlers,zend_get_std_object_handlers(),sizeof(zend_object_handlers))
#define SW_INIT_CLASS_ENTRY_EX(module,name,alias,methods,parent) SW_INIT_CLASS_ENTRY_BASE(module,name,alias,methods,parent##_ce); memcpy(&module##_handlers,&parent##_handlers,sizeof(zend_object_handlers))
#define SW_INIT_CLASS_ENTRY_EX2(module,name,alias,methods,parent,handlers) SW_INIT_CLASS_ENTRY_BASE(module,name,alias,methods,parent); memcpy(&module##_handlers,handlers,sizeof(zend_object_handlers))
#define SW_SET_CLASS_CREATE(module, handler) do { (void)module_number; trace.push_back("create:" #module ":" #handler); } while(false)
#define SW_SET_CLASS_NOT_SERIALIZABLE(module) do { (void)module_number; trace.push_back("not-serializable"); module##_ce->ce_flags|=2; } while(false)
#define SW_SET_CLASS_CLONEABLE(module, handler) trace.push_back("clone:" #handler)
#define SW_SET_CLASS_UNSET_PROPERTY_HANDLER(module, handler) trace.push_back("unset:" #handler)
#define SW_SET_CLASS_CREATE_WITH_ITS_OWN_HANDLERS(module) trace.push_back("own-handlers")
#define SW_SET_CLASS_CUSTOM_OBJECT(module, create, free, structure, field) trace.push_back("custom-object:" #create ":" #free)
#define ZEND_ACC_FINAL 1
#define ZEND_ACC_PRIVATE 4
#define CONST_CS 8
#define CONST_PERSISTENT 16
#define SW_DEFAULT_MAX_CORO_NUM 100000
#define SW_EXIT_IN_COROUTINE 501
#define SW_EXIT_IN_SERVER 502
namespace Coroutine { enum { MAX_NUM_LIMIT=3000000,STATE_INIT=601,STATE_WAITING=602,STATE_RUNNING=603,STATE_END=604 }; }
void zend_register_long_constant(const char *name, size_t length, zend_long value, int flags, int module) {
    assert(length==std::strlen(name) && flags==(CONST_CS|CONST_PERSISTENT));
    trace.push_back("constant:"+std::string(name,length)+":"+std::to_string(value)+":"+std::to_string(module));
}
#define SW_REGISTER_LONG_CONSTANT(name, value) zend_register_long_constant(name,sizeof(name)-1,value,CONST_CS|CONST_PERSISTENT,module_number)
void zend_declare_property_long(zend_class_entry *entry,const char *name,size_t length,zend_long value,int flags) {
    assert(length==std::strlen(name) && flags==ZEND_ACC_PRIVATE && value==0);
    trace.push_back("property:"+std::string(entry->name)+":"+std::string(name,length));
}
#define ZEND_STRL(name) name,sizeof(name)-1
using Callback=void(*)();
void previous_callback() { assert(false); } void coro_exit_handler() { assert(false); }
void coro_begin_silence_handler() { assert(false); } void coro_end_silence_handler() { assert(false); }
void swoole_coroutine_autoload() { assert(false); }
Callback ori_exit_handler, ori_begin_silence_handler, ori_end_silence_handler;
Callback original_zend_autoload, zend_autoload;
#define ZEND_EXIT 1
#define ZEND_BEGIN_SILENCE 2
#define ZEND_END_SILENCE 3
Callback zend_get_user_opcode_handler(int opcode) { trace.push_back("get-opcode:"+std::to_string(opcode)); return previous_callback; }
void zend_set_user_opcode_handler(int opcode, Callback callback) {
    assert(callback==(opcode==1?coro_exit_handler:opcode==2?coro_begin_silence_handler:coro_end_silence_handler));
    trace.push_back("set-opcode:"+std::to_string(opcode));
}
struct { struct { int type; } common; } swoole_coroutine_internal_function;
#define ZEND_INTERNAL_FUNCTION 901
#define SW_FILE_LOCK 1001
namespace zend { void add_constant(const char *name,zend_long value) { zend_register_long_constant(name,std::strlen(name),value,CONST_CS|CONST_PERSISTENT,92); } }
#ifdef SWOOLE_RS_PHPCOROUTINES
#define ZEND_MODULE_API_NO 1
#include "phpcoroutines_registration.h"
#endif
// ACTUAL_BOOTSTRAP_BODIES
int main() {
    static int context_dummy;
    for (unsigned config=0;config<8;++config) for (unsigned kind=0;kind<3;++kind) {
        mode=config%4; registrations=0; globals.use_shortname.value=(mode!=0); globals.cli.value=config&4;
        globals.in_autoload=&context_dummy;
        zend_autoload=previous_callback; original_zend_autoload=nullptr;
        swoole_coroutine_internal_function.common.type=42;
        trace.clear();
        if (kind==0) php_swoole_coroutine_minit(91);
        else if(kind==1) php_swoole_coroutine_scheduler_minit(91);
        else php_swoole_coroutine_system_minit(91);
        std::cout << config << ':' << kind << '\n';
        for(unsigned i=0;i<registrations;++i) std::cout << "class:" << classes[i].name << ':' << classes[i].ce_flags << '\n';
        for(const auto &value:trace) std::cout << value << '\n';
        if(kind==0) {
            assert(zend_autoload==swoole_coroutine_autoload && original_zend_autoload==previous_callback);
            assert(globals.in_autoload==nullptr && swoole_coroutine_internal_function.common.type==ZEND_INTERNAL_FUNCTION);
        }
    }
}
