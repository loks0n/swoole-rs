/* Zend headers for bindgen, plus the macros and inline functions it cannot see.
 * Each shim is the Zend macro it names, compiled against the same headers, so it
 * follows that PHP's version and build mode (ZTS, debug). */
#ifndef SWOOLE_RS_ZEND_SHIM_H
#define SWOOLE_RS_ZEND_SHIM_H
#include "php.h"
#include "zend_exceptions.h"
#include "zend_interfaces.h"

/* zend_object_alloc: emalloc the object and its property slots and zero the
 * bytes before the embedded zend_object. */
void *swr_zend_object_alloc(size_t size, zend_class_entry *ce);

/* INIT_CLASS_ENTRY_EX, then zend_register_internal_class_ex. */
zend_class_entry *swr_zend_register_class(const char *name, size_t length,
                                          const zend_function_entry *functions,
                                          zend_class_entry *parent);

/* ce->create_object, a member of an anonymous union whose bindgen name
 * depends on the PHP version. */
void swr_zend_class_set_create_object(zend_class_entry *ce,
                                      zend_object *(*create)(zend_class_entry *ce));

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

/* emalloc: request memory Zend frees at shutdown even after a bailout. */
void *swr_zend_emalloc(size_t size);

/* efree of a string never shared (zend_string_efree). */
void swr_zend_string_free(zend_string *string);
#endif
