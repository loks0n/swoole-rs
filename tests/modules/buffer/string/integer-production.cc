// Loaded production integer method only: no local String implementation/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(SWR_STRING_APPEND_I32==9,"Integer qualification needs its exact configured edit header");
#endif
#include <dlfcn.h>
#include <exception>
#include <limits>
static unsigned allocated=0,freed=0,resized=0;
static bool fail_next=false;
static void *allocate(size_t n) { void *p=std::malloc(n);if(p) ++allocated;return p; }
static void *resize(void *p,size_t n) { ++resized;if(fail_next) { fail_next=false;return nullptr; }return std::realloc(p,n); }
static void dispose(void *p) { ++freed;std::free(p); }
static const swoole::Allocator allocator{allocate,std::calloc,resize,dispose};
static const char *origin(const char *name) { Dl_info image{};void *p=dlsym(RTLD_DEFAULT,name);return p&&dladdr(p,&image)?image.dli_fname:nullptr; }
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_integer_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_integer_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);allocated=freed=resized=0;fail_next=false;
    const char *method=origin("_ZN6swoole6String6appendEi");
    if(!method) { zend_throw_exception(zend_ce_exception,"Actual integer method unavailable",0);return; }
    add_assoc_string(return_value,"method_image",const_cast<char*>(method));
    for(const char *name:{"swr_v1_string_edit_system","swr_v1_string_apply"}) {
        const char *image=origin(name);if(image) add_assoc_string(return_value,name,const_cast<char*>(image));else add_assoc_null(return_value,name);
    }
    try {
        zval rows;array_init(&rows);
        for(const auto *policy:{sw_std_allocator(),&allocator}) {
            for(int value:{std::numeric_limits<int>::min(),-123456789,-1,0,1,std::numeric_limits<int>::max()}) {
                for(size_t spare:{size_t(0),size_t(2),size_t(11),size_t(16)}) {
                    swoole::String text(32,policy);std::string prefix(text.size-spare,'a');text.append(prefix);text.offset=1;
                    unsigned before=resized;text.append(value);
                    zval row;array_init(&row);add_assoc_stringl(&row,"bytes",text.str,text.length);
                    add_assoc_long(&row,"length",text.length);add_assoc_long(&row,"capacity",text.size);add_assoc_long(&row,"offset",text.offset);
                    add_assoc_bool(&row,"provenance",text.allocator==policy);add_assoc_long(&row,"reallocations",resized-before);
                    add_next_index_zval(&rows,&row);
                }
            }
        }
        add_assoc_zval(return_value,"rows",&rows);
        {
            swoole::String text(8,&allocator);text.append("prefix",6);text.offset=2;
            char *owner=text.str;auto capacity=text.size;unsigned before=resized;fail_next=true;bool caught=false;
            try { text.append(std::numeric_limits<int>::min()); }catch(const std::bad_alloc &) { caught=true; }
            add_assoc_bool(return_value,"failure_caught",caught&&resized==before+1);
            add_assoc_bool(return_value,"failure_unchanged",text.str==owner&&text.size==capacity&&text.length==6&&text.offset==2&&text.to_std_string()=="prefix");
            text.append(-7);add_assoc_stringl(return_value,"after_failure",text.str,text.length);
        }
        add_assoc_long(return_value,"allocations",allocated);add_assoc_long(return_value,"frees",freed);add_assoc_long(return_value,"reallocations",resized);
    } catch(const std::exception &error) { zend_throw_exception(zend_ce_exception,error.what(),0); }
}
static const zend_function_entry integer_functions[]={PHP_FE(swr_integer_production,arginfo_swr_integer_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_integer_production_module_entry={STANDARD_MODULE_HEADER,"swr_integer_production",integer_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_integer_production)
}
