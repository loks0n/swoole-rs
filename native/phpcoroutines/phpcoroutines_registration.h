#ifndef SWOOLE_RS_PHPCOROUTINES_REGISTRATION_H
#define SWOOLE_RS_PHPCOROUTINES_REGISTRATION_H
#include "swoole_rs_phpcoroutines.h"
#if defined(__cplusplus) && defined(ZEND_MODULE_API_NO)
#include <cassert>
// Native Zend allocation/registration boundary. No Rust frame spans this call.
static inline void swr_phpcoroutines_register_class(const swr_phpcoroutines_bootstrap_plan &plan,
                                                   zend_class_entry **slot,
                                                   const zend_function_entry *methods,
                                                   zend_class_entry *const *parent_slot) {
    zend_class_entry entry = {};
    INIT_CLASS_ENTRY_EX(entry, plan.name, plan.length, methods);
    // Preserve the original parent-slot observation after name initialization.
    *slot = zend_register_internal_class_ex(&entry, parent_slot ? *parent_slot : nullptr);
}
#endif
#endif
