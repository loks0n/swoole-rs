/* Actual additive C11 caller: no C++ pointer/length publication policy. */
#include "swoole_rs_utilities.h"
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
_Static_assert(offsetof(struct SwrUtilsSearchResult, pointer) == 0, "pointer layout");
_Static_assert(offsetof(struct SwrUtilsSearchResult, offset) == sizeof(void *), "offset layout");
_Static_assert(offsetof(struct SwrUtilsSearchResult, needle_length) == sizeof(void *) + sizeof(ptrdiff_t), "count layout");
int main(void) {
    assert(swr_v2_utils_ltrim(NULL, 0, 1) == 0);
    assert(swr_v2_utils_rtrim(NULL, 0, 1) == 0);
    char text[] = "\t  a \n";
    char *cursor = text;
    errno = EDOM;
    assert(swr_v2_utils_ltrim(&cursor, 6, 1) == 3);
    assert(cursor == text + 3 && errno == EDOM);
    assert(swr_v2_utils_rtrim(text, 6, 1) == 4);
    assert(text[3] == 'a' && text[4] == 0 && text[5] == 0 && errno == EDOM);
    const char hay[] = "xxababa";
    struct SwrUtilsSearchResult result = swr_v2_utils_search(hay, 7, "aba", 3, 0);
    assert(result.pointer == hay + 2 && result.offset == 2 && result.needle_length == 3);
    result = swr_v2_utils_search(hay, 7, "aba", 0, 2);
    assert(result.pointer == hay + 4 && result.offset == 4 && result.needle_length == 3);
    result = swr_v2_utils_search(hay + 2, 3, "aba", 0, 2);
    assert(result.pointer == NULL && result.offset == -1 && result.needle_length == 3);
    result = swr_v2_utils_search(NULL, 0, "aba", 3, 0);
    assert(result.pointer == NULL && result.offset == -1);
    /* Existing frozen count/sentinel exports remain callable in the same link. */
    assert(swr_v1_utils_find((const uint8_t *) hay, 7, (const uint8_t *) "aba", 3, 0) == 2);
    assert(swr_v1_utils_trim((const uint8_t *) "a ", 2, 1, 1) == 1);
    puts("{\"inline_span_exports\":3,\"c11_checks\":10}");
}
