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

/* zend_string_alloc, zend_string_realloc and zend_string_free, non-persistent. */
zend_string *swr_zend_string_alloc(size_t length);
zend_string *swr_zend_string_realloc(zend_string *string, size_t length);
void swr_zend_string_free(zend_string *string);

/* ZVAL_STR, ZVAL_EMPTY_STRING and ZVAL_EMPTY_ARRAY. */
void swr_zval_str(zval *target, zend_string *string);
void swr_zval_empty_string(zval *target);
void swr_zval_empty_array(zval *target);

/* What PHP's configure found, as SWR_PHP_HAVE_* bits. */
#define SWR_PHP_HAVE_AI_V4MAPPED 1
#define SWR_PHP_HAVE_AI_ALL 2
#define SWR_PHP_HAVE_AI_IDN 4
unsigned swr_php_config(void);

/* emalloc and efree (macros taking file and line in debug builds). */
void *swr_zend_emalloc(size_t size);
void swr_zend_efree(void *ptr);

/* Z_TRY_ADDREF_P and Z_TRY_DELREF_P. */
void swr_zval_try_addref(zval *value);
void swr_zval_try_delref(zval *value);

/* array_init. */
void swr_zend_array_init(zval *value);

/* Swoole's sw_zend_register_class_alias for a name without a leading
 * backslash: a lowercased, interned, persistent alias. */
int swr_zend_register_class_alias(const char *name, size_t length, zend_class_entry *ce);
#endif
