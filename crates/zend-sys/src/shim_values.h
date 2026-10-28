/* Declarations for shim_values.c; included by shim.h. */
#ifndef SWOOLE_RS_ZEND_SHIM_VALUES_H
#define SWOOLE_RS_ZEND_SHIM_VALUES_H
/* zend_string_alloc / RETVAL_STRINGL / RETVAL_STR / array_init / OBJ_RELEASE /
 * GC_ADDREF: inline functions and macros. */
zend_string *swr_zend_string_alloc(size_t length);
void swr_zend_set_stringl(zval *target, const char *bytes, size_t length);
void swr_zend_set_str(zval *target, zend_string *string);
void swr_zend_array_init(zval *target);
void swr_zend_object_release(zend_object *object);
void swr_zend_object_addref(zend_object *object);

/* Z_PARAM_FUNC of argument `num`: false after Zend reported the error. */
bool swr_zend_parse_arg_func(zval *arg, uint32_t num);

/* ZEND_HASH_FOREACH_VAL: `each` returns false to stop. */
void swr_zend_hash_foreach(const HashTable *table, bool (*each)(zval *value, void *context), void *context);

/* zend_hash_str_find(&module_registry, name): whether an extension is loaded. */
bool swr_zend_module_loaded(const char *name, size_t length);

/* zval_get_long, whose slow path's signature depends on the PHP version. */
zend_long swr_zval_get_long(const zval *value);


/* efree of a string never shared (zend_string_efree). */
void swr_zend_string_free(zend_string *string);
/* zend_is_true, whose return type depends on the PHP version. */
bool swr_zend_is_true(const zval *value);
#endif
