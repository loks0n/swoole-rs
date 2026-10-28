#include "shim_http.h"

void swr_zval_stringl(zval *target, const char *bytes, size_t length) {
    ZVAL_STRINGL(target, bytes, length);
}

void swr_zval_copy(zval *target, const zval *source) {
    ZVAL_COPY(target, source);
}
