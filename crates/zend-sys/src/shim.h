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

/* ZVAL_STRINGL: a new string holding a copy of the bytes. */
void swr_zval_stringl(zval *target, const char *bytes, size_t length);

/* ZVAL_EMPTY_STRING: the interned empty string. */
void swr_zval_empty_string(zval *target);

/* ZVAL_COPY: `target` takes a new reference to `source`'s value. */
void swr_zval_copy(zval *target, const zval *source);

/* zval_get_long, whose out-of-line helper's signature changed in PHP 8.3. */
zend_long swr_zval_get_long(const zval *value);
#endif
