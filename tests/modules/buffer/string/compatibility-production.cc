// Readiness only until exact production source/manifest/origins qualify it.
// Ordinary default-allocator operations; no POP/custom/fault/destruction probe.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_string.h"
#include <cstring>
#include <dlfcn.h>
#include <stdexcept>
using swoole::String;
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_compatibility_production,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_compatibility_production) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
#ifdef __APPLE__
    const char *write_symbol="_ZN6swoole6String5writeExPKcm";
#else
    const char *write_symbol="_ZN6swoole6String5writeElPKcm";
#endif
    const char *names[]={"_ZN6swoole6String6appendEPKcm","_ZN6swoole6String6repeatEPKcmm",write_symbol,
        "_ZN6swoole6String4copyERKS0_","_ZN6swoole6String6appendEi","_ZN6swoole6String6reduceEx",
        "swr_v1_string_compat_step"};
#ifndef __APPLE__
    names[5]="_ZN6swoole6String6reduceEl";
#endif
    const char *keys[]={"method_image","repeat_image","write_image","copy_image","integer_image","reduce_image","compat_image"};
    for(unsigned i=0;i<7;++i) {
        Dl_info info{};auto *symbol=dlsym(RTLD_DEFAULT,names[i]);
        if(symbol && dladdr(symbol,&info))add_assoc_string(return_value,keys[i],const_cast<char *>(info.dli_fname));
        else add_assoc_null(return_value,keys[i]);
    }
#if defined(SWOOLE_RS_STRING_DIRECT_FIELDS) && SWOOLE_RS_STRING_DIRECT_FIELDS
    add_assoc_bool(return_value,"direct_fields",true);
    Dl_info fields_info{};auto *fields_symbol=dlsym(RTLD_DEFAULT,"swr_v1_string_fields_step");
    if(fields_symbol && dladdr(fields_symbol,&fields_info))add_assoc_string(return_value,"fields_image",const_cast<char *>(fields_info.dli_fname));
    else add_assoc_null(return_value,"fields_image");
#else
    add_assoc_bool(return_value,"direct_fields",false);
#endif
    try {
    unsigned checks=0;
    auto check=[&](bool value){if(!value)throw std::runtime_error("Positive compatibility assertion");++checks;};
    String append(8);append.append("abc",3);append.offset=1;append.append("defghijkl",9);
    check(append.length==12);check(append.size==16);check(append.offset==1);check(std::memcmp(append.str,"abcdefghijkl",12)==0);
    String source("XYZ",3);append.append(source);
    check(append.length==15);check(std::memcmp(append.str+12,"XYZ",3)==0);
    String write("abc",3);write.offset=1;write.write(1,"XYZ",3);
    check(write.length==4);check(write.offset==1);check(std::memcmp(write.str,"aXYZ",4)==0);
    String integer(8);integer.append("a",1);integer.append(1234567890);
    check(integer.length==11);check(std::memcmp(integer.str,"a1234567890",11)==0);
    String repeated(8);repeated.repeat("abcdefghijklmnopq",17,3);
    check(repeated.length==51);check(repeated.size==56);
    for(unsigned i=0;i<3;++i)check(std::memcmp(repeated.str+i*17,"abcdefghijklmnopq",17)==0);
    String single(8);single.repeat("Z",1,17);check(single.length==17);check(single.size==24);
    for(unsigned i=0;i<17;++i)check(single.str[i]=='Z');
    source.offset=1;String copied(source);check(copied.length==3);check(copied.offset==1);check(std::memcmp(copied.str,"XYZ",3)==0);
    String terminated(8);terminated.append("abcdefgh",8);terminated.set_null_terminated();
    check(terminated.length==8);check(terminated.str[8]==0);check(terminated.size==16);
    String reduced("abcdef",6);reduced.offset=1;reduced.reduce(2);
    check(reduced.length==4);check(reduced.offset==0);check(std::memcmp(reduced.str,"cdef",4)==0);
        add_assoc_long(return_value,"checks",checks);
    } catch(const std::exception &error) {zend_throw_exception(zend_ce_exception,error.what(),0);}
}
static const zend_function_entry compatibility_functions[]={PHP_FE(swr_compatibility_production,arginfo_swr_compatibility_production) PHP_FE_END};
extern "C" {
zend_module_entry swr_compatibility_production_module_entry={STANDARD_MODULE_HEADER,"swr_compatibility_production",compatibility_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_compatibility_production)
}
