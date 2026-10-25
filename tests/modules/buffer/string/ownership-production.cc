// Genuine production assignments; observer reads live metadata before native free.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(SWR_STRING_OWNER_COPY==1 && SWR_STRING_OWNER_MOVE==2,"Ownership qualification needs its exact configured header");
#endif
#include <dlfcn.h>
#include <exception>
#include <unordered_set>
using swoole::String;
namespace {
unsigned frees=0;
std::unordered_set<void *> live;
String *observed=nullptr;
struct Snapshot { char *data; size_t length,capacity; off_t offset; const swoole::Allocator *allocator; } expected;
bool observed_free=false,metadata_equal=true;
void *allocate(size_t size) { void *value=std::malloc(size);if(value)live.insert(value);return value; }
void release(void *value) {
    if(observed && value==expected.data) {
        observed_free=true;
        metadata_equal=observed->str==expected.data && observed->length==expected.length && observed->size==expected.capacity &&
            observed->offset==expected.offset && observed->allocator==expected.allocator;
    }
    live.erase(value);++frees;std::free(value);
}
const swoole::Allocator allocator{allocate,std::calloc,std::realloc,release};
void watch(String &value) { observed=&value;expected={value.str,value.length,value.size,value.offset,value.allocator};observed_free=false;metadata_equal=true; }
const char *origin(const char *name) { Dl_info image{};void *p=dlsym(RTLD_DEFAULT,name);return p&&dladdr(p,&image)?image.dli_fname:nullptr; }
void image(zval *result,const char *key,const char *symbol) { const char *name=origin(symbol);if(name)add_assoc_string(result,key,const_cast<char *>(name));else add_assoc_null(result,key); }
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_ownership_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_ownership_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);frees=0;observed=nullptr;
    image(return_value,"method_image","_ZN6swoole6StringaSERKS0_");
    image(return_value,"move_image","_ZN6swoole6StringaSEOS0_");
    image(return_value,"dispose_image","_ZN6swoole6String7disposeEv");
    image(return_value,"plan_image","swr_v1_string_ownership_plan");
    zval rows;array_init(&rows);
    auto check=[&](bool value) { add_next_index_bool(&rows,value); };
    try {
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;target.append("old",3);target.offset=2;
            watch(target);target=source;observed=nullptr;
            check(observed_free);check(metadata_equal);check(target.length==3 && target.offset==1 && !std::memcmp(target.str,"new",3));
            check(source.length==3 && source.offset==1);
            watch(target);unsigned before=frees;const String *same=&target;target=*same;observed=nullptr;check(!observed_free && frees==before);
        }
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;target.append("old",3);target.offset=2;char *owner=source.str;
            watch(target);target=std::move(source);observed=nullptr;
            check(observed_free);check(metadata_equal);check(target.str==owner && target.length==3 && target.offset==1);
            check(!source.str && !source.length && !source.size && !source.offset && source.allocator==&allocator);
            watch(target);unsigned before=frees;String *same=&target;target=std::move(*same);observed=nullptr;check(!observed_free && frees==before);
        }
        { String target(16,&allocator);target.append("old",3);target.offset=2;watch(target); }
        observed=nullptr;check(observed_free);check(metadata_equal);check(live.empty());
        add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error) { observed=nullptr;zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0); }
}
static const zend_function_entry ownership_functions[]={PHP_FE(swr_ownership_production,arginfo_swr_ownership_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_ownership_production_module_entry={STANDARD_MODULE_HEADER,"swr_ownership_production",ownership_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_ownership_production)
}
