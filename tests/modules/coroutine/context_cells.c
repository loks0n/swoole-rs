/* Ordinary initialized metadata and opaque byte identity only; no Context. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdio.h>
#ifdef SWR_CHANNEL_FFI
#include "swoole_rs.h"
#endif
_Static_assert(sizeof(swr_v1_context_stack_cell) == sizeof(void *), "pointer cell size");
_Static_assert(_Alignof(swr_v1_context_stack_cell) == _Alignof(void *), "pointer alignment");
_Static_assert(sizeof(swr_v1_context_extent) == 4 && _Alignof(swr_v1_context_extent) == 4, "extent cell ABI");
_Static_assert(sizeof(swr_v1_context_completion) == 1 && _Alignof(swr_v1_context_completion) == 1, "completion cell ABI");
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version() == 1 && (swr_v1_feature_bits() & ((uint64_t)1 << 15)));
#endif
    unsigned char bytes[128] = {0};
    swr_v1_context_stack_cell stack;
    swr_v1_context_completion completion;
    swr_v1_context_extent extent = swr_v1_context_extent_new(sizeof bytes);
    assert(swr_v1_context_prepare(&completion, &extent) == sizeof bytes);
    assert(swr_v1_context_completed(&completion) == 0);
    swr_v1_context_stack_view view = swr_v1_context_stack_step(&stack, &extent, SWR_CTX_STACK_ADMIT, bytes, 0);
    assert(view.pointer == bytes && view.size == sizeof bytes && view.present == 1);
    view = swr_v1_context_stack_step(&stack, &extent, SWR_CTX_STACK_TOP, NULL, 0);
    assert(view.pointer == bytes && view.top == bytes + sizeof bytes && view.size == sizeof bytes);
    swr_v1_context_finish(&completion);
    assert(swr_v1_context_completed(&completion) == 1);
    swr_v1_context_stack_step(&stack, &extent, SWR_CTX_STACK_CLEAR, NULL, 0);
    view = swr_v1_context_stack_read(&stack, &extent);
    assert(view.pointer == NULL && view.present == 0 && view.size == sizeof bytes);
    assert(bytes[0] == 0 && bytes[127] == 0);
    swr_v1_context_completion thread_completion;
    assert(swr_v1_context_prepare(&thread_completion, NULL) == 0);
    assert(swr_v1_context_completed(&thread_completion) == 0);
    puts("context-cells-c11:ok");
}
