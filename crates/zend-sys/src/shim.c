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

void swr_zend_set_stringl(zval *target, const char *bytes, size_t length) {
    ZVAL_STRINGL(target, bytes, length);
}

void swr_zend_set_str(zval *target, zend_string *string) {
    ZVAL_STR(target, string);
}

void swr_zend_array_init(zval *target) {
    array_init(target);
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
    ZEND_HASH_FOREACH_VAL(table, value) {
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

void swr_zend_string_free(zend_string *string) {
    efree(string);
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

int swr_zend_register_class_alias(const char *name, size_t length, zend_class_entry *ce) {
    zend_string *alias = zend_string_init(name, length, 1);
    zend_str_tolower(ZSTR_VAL(alias), length);
    alias = zend_new_interned_string(alias);
    return zend_register_class_alias_ex(ZSTR_VAL(alias), ZSTR_LEN(alias), ce, 1);
}
