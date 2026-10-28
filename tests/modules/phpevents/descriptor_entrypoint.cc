// Test-only native ABI consumer. No reactor, callbacks, Event operations or IPC.
#include "php_swoole_private.h"
ZEND_BEGIN_ARG_INFO_EX(arginfo_m28_scalar,0,0,1)
    ZEND_ARG_TYPE_INFO(0, descriptor, IS_LONG, 0)
ZEND_END_ARG_INFO()
ZEND_BEGIN_ARG_INFO_EX(arginfo_m28_stream,0,0,1)
    ZEND_ARG_INFO(0, stream)
ZEND_END_ARG_INFO()
PHP_FUNCTION(m28_scalar_descriptor) {
    zend_long value;
    ZEND_PARSE_PARAMETERS_START(1,1)
        Z_PARAM_LONG(value)
    ZEND_PARSE_PARAMETERS_END();
    zval descriptor;ZVAL_LONG(&descriptor,value);
    RETURN_LONG(php_swoole_convert_to_fd(&descriptor));
}
PHP_FUNCTION(m28_stream_descriptor) {
    zval *stream;
    ZEND_PARSE_PARAMETERS_START(1,1)
        Z_PARAM_RESOURCE(stream)
    ZEND_PARSE_PARAMETERS_END();
    int async=-1;
    const int ordinary=php_swoole_convert_to_fd(stream);
    const int extended=php_swoole_convert_to_fd_ex(stream,&async);
    array_init(return_value);
    add_assoc_bool(return_value,"nonnegative",ordinary>=0 && extended>=0);
    add_assoc_bool(return_value,"same_descriptor",ordinary==extended);
    add_assoc_long(return_value,"async",async);
}
static const zend_function_entry functions[]={
    PHP_FE(m28_scalar_descriptor,arginfo_m28_scalar)
    PHP_FE(m28_stream_descriptor,arginfo_m28_stream)
    PHP_FE_END
};
extern "C" {
zend_module_entry m28_descriptors_module_entry={STANDARD_MODULE_HEADER,"m28_descriptors",functions,nullptr,nullptr,nullptr,nullptr,nullptr,"0",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(m28_descriptors)
}
