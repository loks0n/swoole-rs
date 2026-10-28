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
