// Genuine production copy/assignment methods; no local String source/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(SWR_STRING_COPY == 8, "COPY qualification needs its exact new configured header");
#endif
#include <array>
#include <dlfcn.h>
#include <exception>
static unsigned allocated=0, freed=0, effect_count=0;
static bool fail_next=false;
static swoole::String *offset_effect=nullptr;
static std::array<char,32> effects{};
static void *allocate(size_t size) {
    effects.at(effect_count++)='M';
    if(offset_effect) { offset_effect->offset=1;offset_effect=nullptr; }
    if(fail_next) { fail_next=false; return nullptr; }
    void *p=std::malloc(size); if(p) ++allocated; return p;
}
static void dispose(void *p) { effects.at(effect_count++)='F'; ++freed; std::free(p); }
static const swoole::Allocator allocator{allocate,std::calloc,std::realloc,dispose};
static const char *origin(const char *name) {
    Dl_info image{}; void *method=dlsym(RTLD_DEFAULT,name);
    return method && dladdr(method,&image) ? image.dli_fname : nullptr;
}
static void snapshot(zval *rows,const char *name,const swoole::String &value) {
    zval row; array_init(&row);
    add_assoc_stringl(&row,"bytes",value.str,value.length);
    add_assoc_long(&row,"length",value.length); add_assoc_long(&row,"capacity",value.size);
    add_assoc_long(&row,"offset",value.offset); add_assoc_bool(&row,"custom_allocator",value.allocator==&allocator);
    add_assoc_zval(rows,name,&row);
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_copy_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_copy_production) {
    ZEND_PARSE_PARAMETERS_NONE(); array_init(return_value);
    allocated=freed=effect_count=0; fail_next=false;
    const char *copy_image=origin("_ZN6swoole6String4copyERKS0_");
    const char *assignment_image=origin("_ZN6swoole6StringaSERKS0_");
    const char *system_image=origin("swr_v1_string_edit_system"), *apply_image=origin("swr_v1_string_apply");
    if(!copy_image || !assignment_image) { zend_throw_exception(zend_ce_exception,"Production copy methods unavailable",0); return; }
    add_assoc_string(return_value,"method_image",const_cast<char *>(copy_image));
    add_assoc_string(return_value,"assignment_image",const_cast<char *>(assignment_image));
    if(system_image) add_assoc_string(return_value,"system_image",const_cast<char *>(system_image));
    else add_assoc_null(return_value,"system_image");
    if(apply_image) add_assoc_string(return_value,"apply_image",const_cast<char *>(apply_image));
    else add_assoc_null(return_value,"apply_image");
    try {
        {
            swoole::String source(16,&allocator); source.append("a\0b",3); source.offset=2;
            swoole::String copied(source); snapshot(return_value,"copied",copied);
            add_assoc_bool(return_value,"copy_independent",copied.str!=source.str);
            copied.str[0]='z'; snapshot(return_value,"source_after_copy_write",source);
            swoole::String target(8,&allocator); target.append("old",3);
            unsigned prefix=effect_count; target=source; snapshot(return_value,"assigned",target);
            add_assoc_stringl(return_value,"assignment_effects",effects.data()+prefix,effect_count-prefix);
            char *owner=target.str; prefix=effect_count; auto *same=&target; target=*same;
            add_assoc_bool(return_value,"self_copy_same_owner",target.str==owner);
            add_assoc_long(return_value,"self_copy_effects",effect_count-prefix);
            bool caught=false; prefix=effect_count; fail_next=true;
            try { swoole::String failed(source); } catch(const std::bad_alloc &) { caught=true; }
            add_assoc_bool(return_value,"constructor_oom_caught",caught);
            add_assoc_stringl(return_value,"constructor_oom_effects",effects.data()+prefix,effect_count-prefix);
            snapshot(return_value,"source_after_oom",source);
            source.offset=2;offset_effect=&source;swoole::String fresh(source);
            snapshot(return_value,"fresh_custom_copy",fresh);
            add_assoc_bool(return_value,"custom_source_offset_effect",offset_effect==nullptr && source.offset==1);
        }
        {
            char bytes[8]={'a',0,'b'}; swoole::String borrowed;
            borrowed.str=bytes; borrowed.length=3; borrowed.size=8; borrowed.offset=1;
            swoole::String copied(borrowed); snapshot(return_value,"borrowed_copy",copied);
            add_assoc_bool(return_value,"borrowed_copy_standard",copied.allocator==sw_std_allocator());
            add_assoc_bool(return_value,"borrowed_independent",copied.str!=bytes);
            add_assoc_bool(return_value,"source_stays_borrowed",borrowed.str==bytes && borrowed.allocator==nullptr);
        }
        add_assoc_long(return_value,"native_allocations",allocated); add_assoc_long(return_value,"native_frees",freed);
    } catch(const std::exception &error) { zend_throw_exception(zend_ce_exception,error.what(),0); }
}
static const zend_function_entry copy_functions[]={PHP_FE(swr_copy_production,arginfo_swr_copy_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_copy_production_module_entry={STANDARD_MODULE_HEADER,"swr_copy_production",copy_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_copy_production)
}
