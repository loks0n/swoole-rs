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

void *swr_zend_emalloc(size_t size) {
    return emalloc(size);
}

void swr_zend_efree(void *ptr) {
    efree(ptr);
}

void swr_zval_try_addref(zval *value) {
    Z_TRY_ADDREF_P(value);
}

void swr_zval_try_delref(zval *value) {
    Z_TRY_DELREF_P(value);
}

void swr_zend_array_init(zval *value) {
    array_init(value);
}

zend_string *swr_zend_string_init(const char *text, size_t length) {
    return zend_string_init(text, length, 0);
}

zend_string *swr_zend_string_copy(zend_string *string) {
    return zend_string_copy(string);
}

void swr_zend_string_release(zend_string *string) {
    zend_string_release(string);
}

void swr_zval_str(zval *value, zend_string *string) {
    ZVAL_STR(value, string);
}

int swr_zend_register_class_alias(const char *name, size_t length, zend_class_entry *ce) {
    zend_string *alias = zend_string_init(name, length, 1);
    zend_str_tolower(ZSTR_VAL(alias), length);
    alias = zend_new_interned_string(alias);
    return zend_register_class_alias_ex(ZSTR_VAL(alias), ZSTR_LEN(alias), ce, 1);
}
