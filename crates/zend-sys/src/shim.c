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

void swr_zval_stringl(zval *target, const char *bytes, size_t length) {
    ZVAL_STRINGL(target, bytes, length);
}

void swr_zval_empty_string(zval *target) {
    ZVAL_EMPTY_STRING(target);
}

void swr_zval_copy(zval *target, const zval *source) {
    ZVAL_COPY(target, source);
}

zend_long swr_zval_get_long(const zval *value) {
    return zval_get_long(value);
}
