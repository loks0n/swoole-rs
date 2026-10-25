/* Actual C11 caller of both complete programs; no callbacks/IO/failure probes. */
#include <assert.h>
#include <stddef.h>
#include "swoole_rs_utilities.h"
_Static_assert(sizeof(struct SwrLogFrontdoor) == 8, "frontdoor ABI");
_Static_assert(sizeof(struct SwrLogAction) == 8, "action ABI");
_Static_assert(offsetof(struct SwrLogHex, offset) == 8, "LP64 hex alignment");
_Static_assert(sizeof(struct SwrLogHex) == 40, "LP64 hex ABI");
int main(void) {
    struct SwrLogFrontdoor state = {0};
    struct SwrLogAction action = swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0);
    assert(action.action == 1); /* publish */
    action = swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0);
    assert(action.action == 2); /* threshold */
    action = swr_v2_utils_log_frontdoor_step(&state, 7, 4, 4, 0, 0);
    assert(action.action == 4); /* ignored */
    action = swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0);
    assert(action.action == 5); /* format */
    action = swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0);
    assert(action.action == 6); /* put */
    action = swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0);
    assert(action.action == 0 && state.admitted == 1);
    for (size_t length = 0; length <= 33; ++length) {
        struct SwrLogHex hex = {0};
        int previous = 0;
        size_t bytes = 0, rows = 0, header = 0, footer = 0;
        for (;;) {
            unsigned next = swr_v2_utils_log_hex_step(&hex, length, previous);
            if (!next) break;
            switch (next) {
            case 1: ++header; break;
            case 2: ++bytes; previous = 3; break;
            case 3: previous = (hex.index % 2 == 0); break;
            case 4: case 5: previous = 1; break;
            case 6:
                ++rows;
                assert(hex.hex_length <= 48 && hex.text_length <= 16);
                break;
            case 7: ++footer; break;
            default: assert(0);
            }
        }
        assert(bytes == length && rows == (length + 15) / 16);
        assert(header == 1 && footer == 1);
    }
}
