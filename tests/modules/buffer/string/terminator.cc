// Loaded positive terminator callers; implementation remains in production Swoole.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole_string.h"
#include <dlfcn.h>
#include <exception>
static unsigned allocations=0,frees=0;
static void *allocate(size_t size) { void *p=std::malloc(size); if(p)++allocations; return p; }
static void dispose(void *p) { ++frees; std::free(p); }
static const swoole::Allocator allocator{allocate,std::calloc,std::realloc,dispose};
static const char *origin(const char *name) {
    Dl_info image{};void *method=dlsym(RTLD_DEFAULT,name);
    return method && dladdr(method,&image) ? image.dli_fname : nullptr;
}
static void snapshot(zval *rows,const char *name,const swoole::String &value) {
    zval row;array_init(&row);
    add_assoc_stringl(&row,"bytes",value.str,value.length);
    add_assoc_long(&row,"length",value.length);add_assoc_long(&row,"capacity",value.size);
    add_assoc_long(&row,"offset",value.offset);add_assoc_long(&row,"terminator",static_cast<unsigned char>(value.str[value.length]));
    add_assoc_bool(&row,"allocator_null",value.allocator==nullptr);
    add_assoc_zval(rows,name,&row);
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_terminator_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_terminator_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    const char *image=origin("_ZN6swoole6String6appendEPKcm");
    const char *terminator_image=origin("_ZN6swoole6String19set_null_terminatedEv");
    if(!image) {zend_throw_exception(zend_ce_exception,"Production String append unavailable",0);return;}
    add_assoc_string(return_value,"method_image",const_cast<char*>(image));
    if(terminator_image)add_assoc_string(return_value,"terminator_image",const_cast<char*>(terminator_image));
    else add_assoc_null(return_value,"terminator_image");
    allocations=frees=0;
    try {
        for(bool full:{false,true}) {
            swoole::String value(8,&allocator);const char *bytes=full?"12345678":"abc";
            value.append(bytes,full?8:3);value.offset=1;value.set_null_terminated();
            snapshot(return_value,full?"full":"spare",value);
        }
        char bytes[8]={'a','b','c','z'};
        {
            swoole::String borrowed;borrowed.str=bytes;borrowed.size=sizeof(bytes);borrowed.length=3;borrowed.offset=1;
            borrowed.set_null_terminated();snapshot(return_value,"borrowed",borrowed);
            add_assoc_bool(return_value,"borrowed_pointer_same",borrowed.str==bytes);
        }
        add_assoc_bool(return_value,"borrowed_bytes_after_destructor",!std::memcmp(bytes,"abc\0",4));
        swoole::String text("abc"),binary(std::string("a\0b",3));
        snapshot(return_value,"text_constructor",text);snapshot(return_value,"binary_constructor",binary);
        add_assoc_long(return_value,"native_allocations",allocations);add_assoc_long(return_value,"native_frees",frees);
    }catch(const std::exception&error){zend_throw_exception(zend_ce_exception,error.what(),0);}
}
static const zend_function_entry terminator_functions[]={PHP_FE(swr_terminator_production,arginfo_swr_terminator_production)PHP_FE_END};
extern "C" {
zend_module_entry swr_terminator_production_module_entry={
    STANDARD_MODULE_HEADER,"swr_terminator_production",terminator_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_terminator_production)
}
