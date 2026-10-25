// Loaded production allocation methods; no local String implementation/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(SWR_STRING_ALLOCATION_RESERVE==1,"Allocation qualification requires its actual configured header");
#endif
#include <dlfcn.h>
#include <exception>
#include <utility>
using swoole::String;
namespace {
unsigned mallocs=0,frees=0;
String *observed=nullptr;
bool initial_metadata=false,change_offset=false,fail_resize=false;
void *allocate(size_t size) {
    ++mallocs;
    if(observed)initial_metadata=observed->length==0 && observed->size==size && observed->offset==0;
    return std::malloc(size);
}
void *resize(void *owner,size_t size) {
    if(change_offset && observed)observed->offset=2;
    if(fail_resize)return nullptr;
    return std::realloc(owner,size);
}
void release(void *owner) {++frees;std::free(owner);}
const swoole::Allocator allocator{allocate,std::calloc,resize,release};
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_allocation_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_allocation_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);mallocs=frees=0;observed=nullptr;initial_metadata=change_offset=fail_resize=false;
    for(const auto &entry:{std::pair<const char *,const char *>("method_image","_ZN6swoole6String5allocEmPKNS_9AllocatorE"),
                         {"reserve_image","_ZN6swoole6String7reserveEm"},{"plan_image","swr_v1_string_allocation_plan"}}) {
        Dl_info info{};void *p=dlsym(RTLD_DEFAULT,entry.second);
        if(p && dladdr(p,&info))add_assoc_string(return_value,entry.first,const_cast<char *>(info.dli_fname));else add_assoc_null(return_value,entry.first);
    }
    zval rows;array_init(&rows);auto check=[&](bool value,const char *) {add_next_index_bool(&rows,value);};
    try {
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;target.append("old",3);target.offset=2;
            observed=&target;target=source;observed=nullptr;
            check(initial_metadata,"copy allocation publishes initial scalar metadata before malloc");
            check(target.to_std_string()=="new" && target.length==3 && target.offset==1,"copy publishes live source after allocation");
            check(target.size==16 && target.allocator==&allocator,"copy allocation capacity/provenance");
            observed=&target;change_offset=true;target.reserve(65);change_offset=false;observed=nullptr;
            check(target.size==72,"aligned reserve capacity");
            check(target.length==3 && target.offset==2,"reserve preserves benign native offset effect");
            check(target.to_std_string()=="new" && target.allocator==&allocator,"reserve value/provenance");
            auto *owner=target.str;auto capacity=target.size;fail_resize=true;bool caught=false;
            try {target.reserve(128);}catch(const std::bad_alloc&){caught=true;}
            fail_resize=false;
            check(caught,"reserve OOM remains native exception");
            check(target.str==owner && target.size==capacity && target.length==3 && target.offset==2,"failed reserve prefix retained");
        }
        check(mallocs==3 && frees==3,"custom allocation custody");
        {String empty;empty.reserve(17);check(empty.size==24 && !empty.length && !empty.offset,"empty reserve initializes aligned metadata");check(empty.str && empty.allocator==sw_std_allocator(),"empty reserve selects standard native allocator");}
        {String value(17);check(value.str && value.size==24 && !value.length && !value.offset,"initial aligned allocation");}
        add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error) {observed=nullptr;zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

static const zend_function_entry allocation_functions[]={PHP_FE(swr_allocation_production,arginfo_swr_allocation_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_allocation_production_module_entry={STANDARD_MODULE_HEADER,"swr_allocation_production",allocation_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_allocation_production)
}
