// Loaded whole formatter; native inline ABI caller and actual production methods.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(SWR_STRING_FORMAT_COMMIT==3,"Formatting qualification needs its actual configured header");
#endif
#include <dlfcn.h>
#include <stdexcept>
using swoole::String;
namespace {
unsigned checks=0,allocations=0,frees=0,resizes=0;
bool fail_resize=false,offset_effect=false;
String *observed=nullptr;
void check(bool value,const char *message) {if(!value)throw std::runtime_error(message);++checks;}
void *allocate(size_t size) {auto *p=std::malloc(size);if(p)++allocations;return p;}
void *resize(void *p,size_t size) {++resizes;if(offset_effect && observed)observed->offset=2;if(fail_resize)return nullptr;return std::realloc(p,size);}
void release(void *p) {++frees;std::free(p);}
const swoole::Allocator allocator{allocate,std::calloc,resize,release};
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_format_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_format_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);checks=allocations=frees=resizes=0;fail_resize=offset_effect=false;observed=nullptr;
    const char *names[]={"_ZN6swoole6String7reserveEm","_ZN6swoole6String5allocEmPKNS_9AllocatorE","_ZNK6swoole6String11format_stepEjimm","swr_v1_string_format_step"};
    const char *keys[]={"method_image","alloc_image","step_image","plan_image"};
    for(unsigned i=0;i<4;++i) {
        Dl_info info{};void *p=dlsym(RTLD_DEFAULT,names[i]);
        if(p && dladdr(p,&info))add_assoc_string(return_value,keys[i],const_cast<char *>(info.dli_fname));else add_assoc_null(return_value,keys[i]);
    }
    try {
        for(const auto *policy:{sw_std_allocator(),&allocator}) {
            for(int flags:{0,1,2,3}) {
                for(size_t prefix:{size_t(0),size_t(3),size_t(7)}) {
                    for(size_t width:{size_t(1),size_t(3),size_t(17),size_t(65)}) {
                        String value(8,policy);std::string initial(prefix,'a');value.append(initial);value.offset=1;
                        std::string text(width,'x');const std::string output=text+":-7";
                        std::string expected=(flags&1 ? initial : std::string())+output;
                        size_t capacity=8,needed=expected.size()+1;
                        if(needed>capacity) {if(flags&2){capacity*=2;while(capacity<needed)capacity*=2;}else capacity=(needed+7)&~size_t(7);}
                        auto n=value.format_impl(flags,"%s:%d",text.c_str(),-7);
                        check(n==output.size(),"returned printf count");check(value.to_std_string()==expected,"exact formatted bytes");
                        check(value.length==expected.size(),"exact published length");check(value.size==capacity,"exact capacity policy");
                        check(value.offset==1 && value.allocator==policy,"offset/provenance retained");check(value.str[value.length]==0,"printf terminator");
                    }
                }
                String empty(8,policy);empty.append("old",3);empty.offset=1;auto *owner=empty.str;auto before=resizes;
                check(empty.format_impl(flags,"%s","")==0,"empty sizing return");
                check(empty.str==owner && empty.length==3 && empty.size==8 && empty.offset==1 && empty.to_std_string()=="old" && resizes==before,"empty sizing preserves metadata/value/effects");
                String binary(8,policy);binary.append("a",1);auto n=binary.format_impl(flags,"%c%c",0,'b');
                std::string expected=(flags&1 ? std::string("a") : std::string())+std::string("\0b",2);
                check(n==2 && binary.to_std_string()==expected,"binary printf output");
            }
        }
        {
            String value(8,&allocator);value.append("prefix",6);value.offset=1;auto *owner=value.str;auto before=resizes;
            bool caught=false;fail_resize=true;
            try{value.append_format("%s","a long positive string");}catch(const std::bad_alloc&){caught=true;}
            fail_resize=false;
            check(caught && resizes==before+1,"caught native formatting reserve failure");
            check(value.str==owner && value.length==6 && value.size==8 && value.offset==1 && value.to_std_string()=="prefix","format failure prefix");
            observed=&value;offset_effect=true;value.append_format("%s","a long positive string");offset_effect=false;observed=nullptr;
            check(value.offset==2 && value.to_std_string()=="prefixa long positive string","post-effect offset retained");
        }
        check(allocations==frees,"custom allocation custody");
        add_assoc_long(return_value,"checks",checks);
    } catch(const std::exception &error) {observed=nullptr;zend_throw_exception(zend_ce_exception,error.what(),0);}
}

static const zend_function_entry format_functions[]={PHP_FE(swr_format_production,arginfo_swr_format_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_format_production_module_entry={STANDARD_MODULE_HEADER,"swr_format_production",format_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_format_production)
}
