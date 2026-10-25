/* Ordinary C11 copied-state/opaque-token ABI, never a Native runtime call. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdio.h>
#ifdef SWR_CHANNEL_FFI
#include "swoole_rs.h"
#endif
_Static_assert(sizeof(swr_v1_channel_state) == 16, "qualified prefix");
_Static_assert(_Alignof(swr_v1_channel_state) == 8, "qualified prefix alignment");
_Static_assert(offsetof(swr_v1_channel_state, closed) == 8, "closed offset");
_Static_assert(offsetof(swr_v1_channel_state, error) == 12, "error offset");
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version() == 1);
    assert((swr_v1_feature_bits() & ((uint64_t)1 << 15)) != 0);
#endif
    swr_v1_channel_state state = swr_v1_channel_state_new(1);
    swr_v1_channel_tokens *data = swr_v1_channel_tokens_new();
    swr_v1_channel_tokens *producers = swr_v1_channel_tokens_new();
    swr_v1_channel_tokens *consumers = swr_v1_channel_tokens_new();
    assert(data && producers && consumers);
    int token = 123;
    swr_v1_channel_owned_cursor cursor = {{0}, 0};
    swr_v1_channel_owned_action plan = swr_v1_channel_owned_step(&cursor, &state, data, producers, consumers, SWR_CH_PUSH, 0, &token);
    assert(plan.action == SWR_CH_TRANSFER);
    swr_v1_channel_view view = swr_v1_channel_view_read(&state, data, producers, consumers);
    assert(view.length == 1 && view.full && !view.empty && view.error == 0);
    cursor = (swr_v1_channel_owned_cursor){{0}, 0};
    plan = swr_v1_channel_owned_step(&cursor, &state, data, producers, consumers, SWR_CH_POP, 0, NULL);
    assert(plan.action == SWR_CH_TRANSFER && plan.token == &token && token == 123);
    assert(swr_v1_channel_tokens_push(data, NULL) == 0);
    assert(swr_v1_channel_pop_data(data) == NULL);
    view = swr_v1_channel_view_read(&state, data, producers, consumers);
    assert(view.empty && view.length == 0);
    cursor = (swr_v1_channel_owned_cursor){{0}, 0};
    plan = swr_v1_channel_owned_step(&cursor, &state, data, producers, consumers, SWR_CH_CLOSE, 0, NULL);
    assert(plan.action == SWR_CH_PUBLISH_CLOSED && state.closed == 0);
    plan = swr_v1_channel_owned_step(&cursor, &state, data, producers, consumers, SWR_CH_CLOSE, 0, NULL);
    assert(plan.action == SWR_CH_DONE && state.closed == 1 && state.error == 0);
    cursor = (swr_v1_channel_owned_cursor){{0}, 0};
    plan = swr_v1_channel_owned_step(&cursor, &state, data, producers, consumers, SWR_CH_PUSH, 0, &token);
    assert(plan.action == SWR_CH_ERROR_CLOSED);
    view = swr_v1_channel_view_read(&state, data, producers, consumers);
    assert(view.error == -2 && view.closed && view.empty);
    for (uint32_t role = 1; role <= 2; role++) {
        for (unsigned i = 0; i < 3; i++) {
            swr_v1_channel_waiter_result waiter = swr_v1_channel_waiter(producers, consumers,
                SWR_CH_WAITER_ENQUEUE, role, i == 1 ? NULL : &token);
            assert(waiter.status == 0 && waiter.role == role);
        }
        swr_v1_channel_waiter_result waiter = swr_v1_channel_waiter(producers, consumers,
            SWR_CH_WAITER_REMOVE, role, &token);
        assert(waiter.status == 0 && waiter.role == role);
        waiter = swr_v1_channel_waiter(producers, consumers, SWR_CH_WAITER_POP, role, NULL);
        assert(waiter.status == 0 && waiter.role == role && waiter.token == NULL);
        assert(token == 123);
    }
    view = swr_v1_channel_view_read(&state, data, producers, consumers);
    assert(view.producers == 0 && view.consumers == 0);
    swr_v1_channel_tokens_free(data); swr_v1_channel_tokens_free(producers); swr_v1_channel_tokens_free(consumers);
    puts("channel-state-c11:ok");
}
