/* Corrected-only C11 caller with ordinary uninitialized Native char storage. */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "swoole_rs_utilities.h"
int main(void) {
    const int64_t values[] = {INT64_MIN, -1, 0, 123456, INT64_MAX};
    size_t checks = 0;
    for (size_t capacity = 0; capacity <= 128; capacity++) {
        for (size_t index = 0; index < sizeof(values) / sizeof(*values); index++) {
            uint8_t output[128]; /* No input read or artificial zero-fill. */
            char expected[128];
            int full = snprintf(expected, sizeof(expected), "<.%lld>", (long long) values[index]);
            assert(full >= 0);
            size_t n = swr_v1_utils_log_micros(capacity ? output : NULL, capacity, values[index]);
            if (capacity == 0) assert(n == (size_t) full);
            else {
                size_t count = (size_t) full < capacity ? (size_t) full : capacity - 1;
                assert(n == count && memcmp(output, expected, count) == 0 && output[n] == 0);
            }
            checks++;
        }
        uint8_t output[128];
        const char *expected = "[date *-2147483648.2147483647]\tWARNING\tmessage\n";
        size_t n = swr_v1_utils_log_line(capacity ? output : NULL, capacity,
            (const uint8_t *) "date", -1, '*', INT_MIN, INT_MAX, 4,
            (const uint8_t *) "message", -1);
        if (capacity == 0) assert(n == strlen(expected));
        else {
            size_t count = strlen(expected) < capacity ? strlen(expected) : capacity - 1;
            assert(n == count && memcmp(output, expected, count) == 0 && output[n] == 0);
        }
        checks++;
    }
    printf("{\"c11_uninitialized_output_checks\":%zu}\n", checks);
}
