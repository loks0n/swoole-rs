// Actual production split continuations; no local String implementation/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#ifdef SWOOLE_RS_BUFFER
#include "swoole_rs_string.h"
static_assert(sizeof(swr_v1_string_split_cursor)>0,"Need exact continuation header");
#endif
#include <dlfcn.h>
#include <exception>
#include <stdexcept>
#include <vector>
#ifdef __APPLE__
static const char *split_symbol="_ZN6swoole6String5splitEPKcmRKNSt3__18functionIFbS2_mEEE";
#else
static const char *split_symbol="_ZN6swoole6String5splitEPKcmRKSt8functionIFbS2_mEE";
#endif
static const char *origin(const char *name) {
    Dl_info image{}; void *method=dlsym(RTLD_DEFAULT,name);
    return method && dladdr(method,&image) ? image.dli_fname : nullptr;
}
static void packets(zval *rows,const char *name,const std::vector<std::string> &values) {
    zval row; array_init(&row);
    for(const auto &v:values)add_next_index_stringl(&row,v.data(),v.size());
    add_assoc_zval(rows,name,&row);
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_split_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_split_production) {
    ZEND_PARSE_PARAMETERS_NONE(); array_init(return_value);
    const char *method=origin(split_symbol), *plan=origin("swr_v1_string_split_plan");
    if(!method) { zend_throw_exception(zend_ce_exception,"Production split method unavailable",0);return; }
#ifdef SWOOLE_RS_BUFFER
    if(!plan) { zend_throw_exception(zend_ce_exception,"Production continuation planner unavailable",0);return; }
#endif
    add_assoc_string(return_value,"method_image",const_cast<char *>(method));
    if(plan)add_assoc_string(return_value,"plan_image",const_cast<char *>(plan));else add_assoc_null(return_value,"plan_image");
    try {
        {
            swoole::String value("xxone\r\n"); value.offset=2; std::string frame;
            auto result=value.split("\r\n",2,[&](const char *p,size_t n){frame.assign(p,n);value.offset=3;return false;});
            add_assoc_stringl(return_value,"false_frame",frame.data(),frame.size());
            add_assoc_long(return_value,"false_result",result);add_assoc_long(return_value,"false_offset",value.offset);
            value.offset=2;bool caught=false;
            try { value.split("\r\n",2,[&](const char *,size_t)->bool{value.offset=4;throw std::runtime_error("callback");}); }
            catch(const std::runtime_error &){caught=true;}
            add_assoc_bool(return_value,"throw_caught",caught);add_assoc_long(return_value,"throw_offset",value.offset);
        }
        {
            swoole::String value("one\r\n");std::vector<std::string> seen;
            auto result=value.split("\r\n",2,[&](const char *p,size_t n){seen.emplace_back(p,n);if(seen.size()==1)value.append("two\r\n",5);return true;});
            packets(return_value,"append_packets",seen);add_assoc_long(return_value,"append_result",result);add_assoc_long(return_value,"append_offset",value.offset);
        }
        {
            swoole::String value("a\r\nb\r\n");std::vector<std::string> seen;
            auto result=value.split("\r\n",2,[&](const char *p,size_t n){seen.emplace_back(p,n);if(seen.size()==1)value.str[3]='c';return true;});
            packets(return_value,"mutated_packets",seen);add_assoc_long(return_value,"mutated_result",result);add_assoc_long(return_value,"mutated_offset",value.offset);
        }
        {
            swoole::String value("a\r\nb\r\n");unsigned calls=0;
            auto result=value.split("\r\n",2,[&](const char *,size_t){++calls;value.offset=3;return true;});
            add_assoc_long(return_value,"offset_callbacks",calls);add_assoc_long(return_value,"offset_result",result);add_assoc_long(return_value,"offset_offset",value.offset);
        }
        {
            swoole::String value(std::string("a\0b\r\ntrail",10));std::vector<std::string> seen;
            auto result=value.split("\r\n",2,[&](const char *p,size_t n){seen.emplace_back(p,n);return true;});
            packets(return_value,"binary_packets",seen);add_assoc_long(return_value,"binary_result",result);add_assoc_long(return_value,"binary_offset",value.offset);
            value.reduce(result);add_assoc_stringl(return_value,"residual",value.str,value.length);add_assoc_long(return_value,"residual_offset",value.offset);
        }
    }catch(const std::exception &error){zend_throw_exception(zend_ce_exception,error.what(),0);}
}
static const zend_function_entry split_functions[]={PHP_FE(swr_split_production,arginfo_swr_split_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_split_production_module_entry={STANDARD_MODULE_HEADER,"swr_split_production",split_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_split_production)
}
