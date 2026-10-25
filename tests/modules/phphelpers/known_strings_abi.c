/* Positive frozen C11 caller contract only; no Zend/runtime/lifetime effects. */
#include "swoole_rs_phphelpers.h"
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
int main(void) {
    size_t cursor = 0;
    const size_t count = swr_v1_phphelpers_known_count();
    for (size_t index = 0; index < count; ++index) {
        size_t length; /* Corrected implementation writes this output directly. */
        const char *name = swr_v1_phphelpers_known_next(&cursor, &length);
        assert(name && strlen(name) == length && cursor == index + 1);
    }
    size_t length = 73;
    assert(!swr_v1_phphelpers_known_next(&cursor, &length));
    assert(cursor == count && length == 73);
    printf("{\"known_strings\":%zu,\"native_runtime_executed\":false}\n", count);
    return 0;
}
