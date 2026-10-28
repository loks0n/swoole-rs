#include "shim.h"

void *swr_zend_object_alloc(size_t size, zend_class_entry *ce) {
    return zend_object_alloc(size, ce);
}

zend_class_entry *swr_zend_register_class(const char *name, size_t length,
                                          const zend_function_entry *functions,
                                          zend_class_entry *parent) {
    zend_class_entry ce;
    INIT_CLASS_ENTRY_EX(ce, name, length, functions);
    return zend_register_internal_class_ex(&ce, parent);
}

void swr_zend_class_set_create_object(zend_class_entry *ce,
                                      zend_object *(*create)(zend_class_entry *ce)) {
    ce->create_object = create;
}

zend_string *swr_zend_string_alloc(size_t length) {
    return zend_string_alloc(length, 0);
}

zend_string *swr_zend_string_realloc(zend_string *string, size_t length) {
    return zend_string_realloc(string, length, 0);
}

void swr_zend_string_free(zend_string *string) {
    zend_string_free(string);
}

void swr_zval_str(zval *target, zend_string *string) {
    ZVAL_STR(target, string);
}

void swr_zval_empty_string(zval *target) {
    ZVAL_EMPTY_STRING(target);
}

void swr_zval_array_init(zval *target) {
    array_init(target);
}

void swr_zval_empty_array(zval *target) {
    ZVAL_EMPTY_ARRAY(target);
}

int swr_zend_register_class_alias(const char *name, size_t length, zend_class_entry *ce) {
    zend_string *alias = zend_string_init(name, length, 1);
    if (name[0] == '\\') {
        zend_str_tolower_copy(ZSTR_VAL(alias), name + 1, length - 1);
    } else {
        zend_str_tolower_copy(ZSTR_VAL(alias), name, length);
    }
    alias = zend_new_interned_string(alias);
    return zend_register_class_alias_ex(ZSTR_VAL(alias), ZSTR_LEN(alias), ce, 1);
}

unsigned swr_php_config(void) {
    unsigned found = 0;
#if HAVE_AI_V4MAPPED
    found |= SWR_PHP_HAVE_AI_V4MAPPED;
#endif
#if HAVE_AI_ALL
    found |= SWR_PHP_HAVE_AI_ALL;
#endif
#if HAVE_AI_IDN
    found |= SWR_PHP_HAVE_AI_IDN;
#endif
    return found;
}
