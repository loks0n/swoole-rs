/* Ordinary initialized lifecycle POD/decision ABI only. No Native effects. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdio.h>
#ifdef SWR_CHANNEL_FFI
#include "swoole_rs.h"
#endif
_Static_assert(sizeof(swr_v1_coroutine_status) == 8, "coupled status size");
_Static_assert(_Alignof(swr_v1_coroutine_status) == 4, "coupled status alignment");
_Static_assert(offsetof(swr_v1_coroutine_status, code) == 4, "resume offset");
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version() == 1 && (swr_v1_feature_bits() & ((uint64_t)1 << 15)));
#endif
    for (uint32_t op = 0; op < 8; op++) {
        for (uint32_t facts = 0; facts < 64; facts++) {
            for (int32_t code = -2; code <= 0; code++) {
                swr_v1_coroutine_status status = {2, code};
                swr_v1_coroutine_plan expected = swr_v1_coroutine_transition(op, facts, code);
                swr_v1_coroutine_plan actual = swr_v1_coroutine_status_transition(&status, op, facts, SWR_CO_STATUS_DECIDE);
                assert(actual.actions == expected.actions && actual.state == expected.state && actual.resume_code == expected.resume_code && actual.error == expected.error);
                assert(status.state == 2 && status.code == code);
                actual = swr_v1_coroutine_status_transition(&status, op, facts, SWR_CO_STATUS_PUBLISH);
                assert(actual.actions == expected.actions && actual.state == expected.state && actual.resume_code == expected.resume_code && actual.error == expected.error);
                assert(status.state == (expected.state == -1 ? 2 : expected.state));
                assert(status.code == (expected.resume_code == INT32_MIN ? code : expected.resume_code));
                swr_v1_coroutine_status_view view = swr_v1_coroutine_status_read(&status);
                assert(view.state == status.state && view.code == status.code);
                assert(view.canceled == (status.code == -2) && view.timedout == (status.code == -1) && view.suspending == (status.state == 1));
            }
        }
    }
    swr_v1_coroutine_status status = {1, 0};
    swr_v1_coroutine_status_transition(&status, SWR_CO_CANCEL, SWR_CO_CANCELABLE, SWR_CO_STATUS_DECIDE);
    assert(status.code == 0);
    swr_v1_coroutine_status_transition(&status, SWR_CO_CANCEL, SWR_CO_CANCELABLE, SWR_CO_STATUS_PUBLISH);
    assert(status.code == -2);
    swr_v1_coroutine_status_transition(&status, SWR_CO_STATUS_TIMEOUT, 0, SWR_CO_STATUS_PUBLISH);
    assert(status.code == -1 && status.state == 1);
    puts("coroutine-status-c11:1536-decisions/commits:ok");
}
