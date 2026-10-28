/* Callables kept past a call (timer and event callbacks), and Swoole's global
 * function aliases of static methods. Included by shim.h for bindgen. */
#ifndef SWOOLE_RS_ZEND_CALLABLE_H
#define SWOOLE_RS_ZEND_CALLABLE_H
#include "php.h"
#include "zend_closures.h"

/* Swoole's zend::Function, whose layout it shares. */
typedef struct {
    zend_fcall_info fci;
    zend_fcall_info_cache fcc;
} swr_zend_callable;
/* sw_zend_fci_cache_persist: hold the bound object and closure. */
void swr_zend_callable_hold(swr_zend_callable *callable);
/* sw_zend_fci_params_discard, then sw_zend_fci_cache_discard; may run PHP
 * destructors, so Rust runs it under swr_zend_try. */
void swr_zend_callable_release(void *callable);

/* Swoole's sw_zend_register_function_alias: register `alias` in the global
 * function table with the handler of `ce`'s method `origin`. */
int swr_zend_register_function_alias(zend_class_entry *ce, const char *origin, size_t origin_length,
                                     const char *alias, size_t alias_length,
                                     const zend_internal_arg_info *arg_info);
#endif
