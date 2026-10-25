#pragma once
#include "swoole_rs_buffer.h"
#ifdef __cplusplus
extern "C" {
#endif
/* front kind: 1=native token, 2=publish embedded view, 3=cached embedded view.
 * EMPTY zeroes output. The stable view address is identity only, never read. */
int32_t swr_v1_buffer_front_plan(swr_v1_buffer *, void *facade_view, swr_v1_buffer_view *);
typedef struct swr_v1_buffer_advance_result {
    uint32_t action; /* 0=stop, 1=call cached destroy before detach, 2=detached */
    uint32_t reset_view;
    void *token;
} swr_v1_buffer_advance_result;
/* drain and cached_destroy are booleans. Rust returns before native effects. */
int32_t swr_v1_buffer_advance(swr_v1_buffer *, uint32_t drain, uint32_t cached_destroy,
                            swr_v1_buffer_advance_result *);
#ifdef __cplusplus
}
#endif
