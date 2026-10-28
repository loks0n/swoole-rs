#include "shim.h"

zend_string *swr_zend_string_alloc(size_t length) {
    return zend_string_alloc(length, 0);
}

zend_string *swr_zend_string_realloc(zend_string *string, size_t length) {
    return zend_string_realloc(string, length, 0);
}

void swr_zend_string_free(zend_string *string) {
    zend_string_free(string);
}

void swr_zval_empty_string(zval *target) {
    ZVAL_EMPTY_STRING(target);
}

void swr_zval_empty_array(zval *target) {
    ZVAL_EMPTY_ARRAY(target);
}
