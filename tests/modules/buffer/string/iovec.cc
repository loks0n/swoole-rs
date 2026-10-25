// Positive loaded POSIX vector callers, no local Buffer implementation/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_buffer.h"
#include <array>
#include <cstddef>
#include <dlfcn.h>
#include <exception>
#include <string>
static const char *origin(const char *name) {
    Dl_info image{}; void *method = dlsym(RTLD_DEFAULT, name);
    return method && dladdr(method, &image) ? image.dli_fname : nullptr;
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_iovec_production, 0, 0, IS_ARRAY, 0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_iovec_production) {
    ZEND_PARSE_PARAMETERS_NONE(); array_init(return_value);
#ifdef __APPLE__
    const char *method = "_ZN6swoole6Buffer6appendEPK5iovecmx";
#else
    const char *method = "_ZN6swoole6Buffer6appendEPK5iovecml";
#endif
    const char *image = origin(method), *rust_image = origin("swr_v1_buffer_append_iovec");
    if (!image) { zend_throw_exception(zend_ce_exception, "Production POSIX vector method unavailable", 0); return; }
    add_assoc_string(return_value, "method_image", const_cast<char *>(image));
    if (rust_image) add_assoc_string(return_value, "rust_image", const_cast<char *>(rust_image));
    else add_assoc_null(return_value, "rust_image");
    add_assoc_long(return_value, "iovec_size", sizeof(iovec));
    add_assoc_long(return_value, "iovec_alignment", alignof(iovec));
    add_assoc_long(return_value, "base_offset", offsetof(iovec, iov_base));
    add_assoc_long(return_value, "length_offset", offsetof(iovec, iov_len));
    try {
        zval cases; array_init(&cases);
        for (unsigned count : {1u,8u,9u,32u}) {
            std::array<std::array<char,3>,32> bytes{};
            std::array<iovec,32> parts{};
            for (unsigned i=0; i<count; ++i) {
                bytes[i] = {char(0),char(i),char(255)};
                parts[i] = {bytes[i].data(),bytes[i].size()};
            }
            for (unsigned chunk : {0u,1u,4u}) {
                swoole::Buffer buffer(chunk); buffer.append(parts.data(),count,0);
                zval row; array_init(&row);
                add_assoc_long(&row,"count",count); add_assoc_long(&row,"chunk",chunk);
                add_assoc_long(&row,"initial_length",buffer.length());
                add_assoc_long(&row,"initial_count",buffer.count());
                std::string joined;
                zval lengths; array_init(&lengths);
                while (!buffer.empty()) {
                    auto *front=buffer.front(); joined.append(front->value.str,front->length);
                    buffer.pop(); add_next_index_long(&lengths,buffer.length());
                }
                add_assoc_stringl(&row,"bytes",joined.data(),joined.size());
                add_assoc_zval(&row,"lengths_after_pop",&lengths);
                add_assoc_long(&row,"final_count",buffer.count());
                add_next_index_zval(&cases,&row);
            }
        }
        add_assoc_zval(return_value,"cases",&cases);
    } catch (const std::exception &error) { zend_throw_exception(zend_ce_exception,error.what(),0); }
}
static const zend_function_entry iovec_functions[] = { PHP_FE(swr_iovec_production,arginfo_swr_iovec_production) PHP_FE_END };
extern "C" {
zend_module_entry swr_iovec_production_module_entry = {
    STANDARD_MODULE_HEADER,"swr_iovec_production",iovec_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_iovec_production)
}
