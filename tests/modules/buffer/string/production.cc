// A test-only PHP addon calling the loaded production String implementation.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole_string.h"
#include <dlfcn.h>
#include <exception>

ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_string_production, 0, 0, IS_ARRAY, 0)
ZEND_END_ARG_INFO()

PHP_FUNCTION(swr_string_production) {
    ZEND_PARSE_PARAMETERS_NONE();
    array_init(return_value);
    Dl_info origin{};
    void *symbol = dlsym(RTLD_DEFAULT, "_ZN6swoole6String19append_random_bytesEmb");
    if (!symbol || !dladdr(symbol, &origin) || !origin.dli_fname) {
        zend_throw_exception(zend_ce_exception, "Production String method is unavailable", 0);
        return;
    }
    add_assoc_string(return_value, "method_image", const_cast<char *>(origin.dli_fname));
    add_assoc_long(return_value, "alignment", SW_DEFAULT_ALIGNMENT);
    add_assoc_long(return_value, "page_size", swoole_pagesize());
    zval rows;
    array_init(&rows);
    try {
        for (bool encoded : {false, true}) {
            for (size_t requested : {size_t(1), size_t(2), size_t(3), size_t(4), size_t(7), size_t(16), size_t(63), size_t(1024)}) {
                swoole::String value(16);
                const char prefix[] = {'p', '\0', 'f', 'x', char(255)};
                value.append(prefix, sizeof(prefix));
                value.offset = 1;
                const size_t initial_capacity = value.size;
                const bool success = value.append_random_bytes(requested, encoded);
                zval row;
                array_init(&row);
                add_assoc_bool(&row, "encoded", encoded);
                add_assoc_long(&row, "requested", requested);
                add_assoc_long(&row, "initial_capacity", initial_capacity);
                add_assoc_bool(&row, "success", success);
                add_assoc_long(&row, "length", value.length);
                add_assoc_long(&row, "capacity", value.size);
                add_assoc_long(&row, "offset", value.offset);
                add_assoc_stringl(&row, "bytes", value.str, value.length);
                const bool next_success = value.append_random_bytes(3, false);
                add_assoc_bool(&row, "next_success", next_success);
                add_assoc_long(&row, "next_length", value.length);
                add_assoc_long(&row, "next_offset", value.offset);
                add_assoc_stringl(&row, "next_bytes", value.str, value.length);
                add_next_index_zval(&rows, &row);
            }
        }
    } catch (const std::exception &error) {
        zval_ptr_dtor(&rows);
        zend_throw_exception(zend_ce_exception, error.what(), 0);
        return;
    }
    add_assoc_zval(return_value, "rows", &rows);
}

static const zend_function_entry production_functions[] = {
    PHP_FE(swr_string_production, arginfo_swr_string_production)
    PHP_FE_END
};

extern "C" {
zend_module_entry swr_string_production_module_entry = {
    STANDARD_MODULE_HEADER,
    "swr_string_production",
    production_functions,
    nullptr, nullptr, nullptr, nullptr, nullptr,
    "1", STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_string_production)
}
