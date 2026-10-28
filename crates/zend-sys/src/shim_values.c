/* Value, string, array and object helpers (crates/phpprocess and later families). */
#include "shim.h"

void swr_zend_set_stringl(zval *target, const char *bytes, size_t length) {
    ZVAL_STRINGL(target, bytes, length);
}

void swr_zend_set_str(zval *target, zend_string *string) {
    ZVAL_STR(target, string);
}

void swr_zend_object_release(zend_object *object) {
    OBJ_RELEASE(object);
}

void swr_zend_object_addref(zend_object *object) {
    GC_ADDREF(object);
}

bool swr_zend_parse_arg_func(zval *arg, uint32_t num) {
    zend_fcall_info fci;
    zend_fcall_info_cache fcc;
    char *error = NULL;
#ifdef Z_PARAM_FUNC_NO_TRAMPOLINE_FREE
    if (zend_parse_arg_func(arg, &fci, &fcc, 0, &error, 1)) {
#else
    if (zend_parse_arg_func(arg, &fci, &fcc, 0, &error)) {
#endif
        return 1;
    }
    zend_wrong_parameter_error(error ? ZPP_ERROR_WRONG_CALLBACK : ZPP_ERROR_WRONG_ARG, num, error, Z_EXPECTED_FUNC, arg);
    return 0;
}

void swr_zend_hash_foreach(const HashTable *table, bool (*each)(zval *value, void *context), void *context) {
    zval *value;
    ZEND_HASH_FOREACH_VAL((HashTable *) table, value) {
        if (!each(value, context)) {
            break;
        }
    }
    ZEND_HASH_FOREACH_END();
}

bool swr_zend_module_loaded(const char *name, size_t length) {
    return zend_hash_str_find(&module_registry, name, length) != NULL;
}

zend_long swr_zval_get_long(const zval *value) {
    return zval_get_long(value);
}

bool swr_zend_is_true(const zval *value) {
    return zend_is_true((zval *) value);
}
