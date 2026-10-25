/* Additive copied-scalar C11 ABI; no callbacks or external effects. */
#include "swoole_rs_phphelpers.h"
#include <assert.h>
#ifdef SWR_PHPHELPERS_FFI
#include "swoole_rs.h"
#endif
int main(void) {
#ifdef SWR_PHPHELPERS_FFI
    assert(swr_v1_abi_version() == 1);
    assert((swr_v1_feature_bits() & ((uint64_t)1 << 24)) != 0);
#endif
    uint32_t phase = 0;
    assert(swr_v1_phphelpers_async(&phase, 1, 0) == SWR_PHP_ASYNC_DIRECT);
    phase = 0;
    assert(swr_v1_phphelpers_async(&phase, 0, 0) == SWR_PHP_ASYNC_OBSERVE_COROUTINE);
    assert(swr_v1_phphelpers_async(&phase, 0, 1) == SWR_PHP_ASYNC_DISPATCH);
    phase = 0;
    assert(swr_v1_phphelpers_async(&phase, 0, 0) == SWR_PHP_ASYNC_OBSERVE_COROUTINE);
    assert(swr_v1_phphelpers_async(&phase, 0, 0) == SWR_PHP_ASYNC_DIRECT);
    return 0;
}
