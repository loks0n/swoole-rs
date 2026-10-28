/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_COROUTINE_H
#define SWOOLE_RS_COROUTINE_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Copied snapshots, never native layouts. No callbacks, allocation or errno. */
enum swr_coroutine_operation {
    SWR_CO_RUN = 0, SWR_CO_RESUME = 1, SWR_CO_YIELD = 2,
    SWR_CO_CANCEL = 3, SWR_CO_CLOSE = 4, SWR_CO_CHECK_END = 5,
    SWR_CO_WAIT_BEFORE_DELETE = 6, SWR_CO_WAIT_AFTER_DELETE = 7
};
enum swr_coroutine_fact {
    SWR_CO_BAILOUT = 1, SWR_CO_CALLBACK = 2, SWR_CO_TASK = 4,
    SWR_CO_CANCELABLE = 8, SWR_CO_ENDED = 16, SWR_CO_TIMER = 32
};
enum swr_coroutine_action {
    SWR_CO_PROCEED = 1, SWR_CO_CALL = 2, SWR_CO_CLEAR_CANCEL = 4,
    SWR_CO_DELETE_TIMER = 8, SWR_CO_DESTROY = 16, SWR_CO_CALL_BAILOUT = 32
};
typedef struct { long value; } swr_v1_coroutine_cid;
typedef struct { uint32_t phase; } swr_v1_coroutine_creation_cursor;
typedef struct { int32_t action; long cid; } swr_v1_coroutine_creation_action;
enum { SWR_CO_CREATE_DONE=0, SWR_CO_CREATE_INSERT=1, SWR_CO_CREATE_COUNT=2, SWR_CO_CREATE_ACTIVATE=3,
       SWR_CO_CREATE_ALLOCATION=-3, SWR_CO_CREATE_INVALID=-4 };
long swr_v1_coroutine_cid_read(const swr_v1_coroutine_cid *);

typedef struct { void *token; } swr_v1_coroutine_identity;
enum { SWR_CO_IDENTITY_ENTER = 0, SWR_CO_IDENTITY_LEAVE = 1 };
void *swr_v1_coroutine_identity_read(const swr_v1_coroutine_identity *);
void swr_v1_coroutine_identity_publish(swr_v1_coroutine_identity *, void *);
/* Whole entry effects: available/init/activate/create/wait/deactivate/done. */
typedef struct { uint32_t mode, phase; uint8_t managed; long cid; } swr_v1_coroutine_entry_cursor;
typedef struct { uint32_t action; long result; } swr_v1_coroutine_entry_action;
swr_v1_coroutine_entry_action swr_v1_coroutine_entry_step(swr_v1_coroutine_entry_cursor *, long);
/* Designated foreign-origin cell walk only; Native supplies exact live offset. */
typedef struct { void *saved; uint32_t phase; } swr_v1_coroutine_bailout_cursor;
typedef struct { uint32_t action; void *coroutine; } swr_v1_coroutine_bailout_action;
swr_v1_coroutine_bailout_action swr_v1_coroutine_bailout_step(swr_v1_coroutine_bailout_cursor *, const swr_v1_coroutine_identity *, uint8_t, size_t);
void swr_v1_coroutine_identity_route(swr_v1_coroutine_identity *, swr_v1_coroutine_identity *, void *, uint32_t);

typedef struct { uint32_t actions; int32_t state, resume_code, error; } swr_v1_coroutine_plan;
swr_v1_coroutine_plan swr_v1_coroutine_transition(uint32_t op, uint32_t facts, int32_t code);
typedef void (*swr_v1_coroutine_swap_function)(void *);
typedef struct { swr_v1_coroutine_swap_function function; } swr_v1_coroutine_swap_callback;
typedef struct { swr_v1_coroutine_plan plan; swr_v1_coroutine_swap_function function; void *task; } swr_v1_coroutine_dispatch_result;
void swr_v1_coroutine_swap_publish(swr_v1_coroutine_swap_callback *, swr_v1_coroutine_swap_function);

/* Caller-local cursor. Native publishes one action and refreshes facts after
 * every timer/queue/callback operation. No borrow crosses native execution. */
typedef struct { uint32_t phase; } swr_v1_channel_cursor;
enum swr_channel_operation { SWR_CH_PUSH = 0, SWR_CH_POP = 1, SWR_CH_CLOSE = 2 };
enum swr_channel_fact {
    SWR_CH_CLOSED = 1, SWR_CH_EMPTY = 2, SWR_CH_FULL = 4,
    SWR_CH_PRODUCERS = 8, SWR_CH_CONSUMERS = 16, SWR_CH_POSITIVE_TIMEOUT = 32,
    SWR_CH_TIMER = 64, SWR_CH_CANCELED = 128, SWR_CH_TIMEDOUT = 256
};
enum swr_channel_action {
    SWR_CH_DONE = 0, SWR_CH_ARM_TIMER = 1, SWR_CH_YIELD = 2,
    SWR_CH_DELETE_TIMER = 3, SWR_CH_TRANSFER = 4, SWR_CH_WAKE_PRODUCER = 5,
    SWR_CH_WAKE_CONSUMER = 6, SWR_CH_PUBLISH_CLOSED = 7,
    SWR_CH_ERROR_TIMEOUT = -1, SWR_CH_ERROR_CLOSED = -2,
    SWR_CH_ERROR_CANCELED = -3, SWR_CH_INVALID = -4
};
int32_t swr_v1_channel_step(swr_v1_channel_cursor *, uint32_t op, uint32_t facts);
/* Sole pointer-token FIFOs. Native owns payloads and translates allocation
 * failures after return. Each call requires a live, exclusively accessed owner. */
typedef struct swr_v1_channel_tokens swr_v1_channel_tokens;
swr_v1_channel_tokens *swr_v1_channel_tokens_new(void);
swr_v1_channel_tokens *swr_v1_channel_tokens_clone(const swr_v1_channel_tokens *);
void swr_v1_channel_tokens_free(swr_v1_channel_tokens *);
size_t swr_v1_channel_tokens_len(const swr_v1_channel_tokens *);
int32_t swr_v1_channel_tokens_push(swr_v1_channel_tokens *, void *);
int32_t swr_v1_channel_tokens_front(const swr_v1_channel_tokens *, void **);
void swr_v1_channel_tokens_pop(swr_v1_channel_tokens *);
void swr_v1_channel_tokens_remove(swr_v1_channel_tokens *, void *);
/* Whole inline Channel metadata; passive initialized POD copy is allowed.
 * Native Channel prefix/queue offsets are statically qualified in its header.
 * State/three queue handles are disjoint and initialized; no pointee or effect
 * enters Rust. All borrows end before Native logging/timer/yield/resume. */
typedef struct { size_t capacity; uint8_t closed; int32_t error; } swr_v1_channel_state;
typedef struct { size_t length, producers, consumers; int32_t error;
                 uint8_t closed, full, empty; } swr_v1_channel_view;
typedef struct { swr_v1_channel_cursor step; uint32_t pending; } swr_v1_channel_owned_cursor;
typedef struct { int32_t action; void *token; } swr_v1_channel_owned_action;
enum { SWR_CH_ALLOCATION_REFUSED = -5 };
swr_v1_channel_state swr_v1_channel_state_new(size_t capacity);
swr_v1_channel_view swr_v1_channel_view_read(const swr_v1_channel_state *,
    const swr_v1_channel_tokens *data, const swr_v1_channel_tokens *producers,
    const swr_v1_channel_tokens *consumers);
void *swr_v1_channel_pop_data(swr_v1_channel_tokens *data);
/* Complete waiter operation: enqueue/pop select producer only for role1;
 * remove selects consumer only for role2. Removal erases ALL matching identities.
 * Native retains tracing, timers, callbacks, yield/resume and bad_alloc effects. */
typedef struct { int32_t status; uint32_t role; void *token; } swr_v1_channel_waiter_result;
enum { SWR_CH_WAITER_ENQUEUE = 0, SWR_CH_WAITER_REMOVE = 1, SWR_CH_WAITER_POP = 2 };
swr_v1_channel_waiter_result swr_v1_channel_waiter(swr_v1_channel_tokens *producers,
    swr_v1_channel_tokens *consumers, uint32_t operation, uint32_t role, void *token);
/* Sole initialized inline Coroutine lifecycle record; original public enums and
 * complete class offsets remain frozen. Native seeds INIT/OK as constants. */
typedef struct { int32_t state, code; } swr_v1_coroutine_status;
typedef struct { int32_t state, code; uint8_t canceled, timedout, suspending; } swr_v1_coroutine_status_view;
enum { SWR_CO_STATUS_DECIDE = 0, SWR_CO_STATUS_PUBLISH = 1, SWR_CO_STATUS_TIMEOUT = 8 };
swr_v1_coroutine_status_view swr_v1_coroutine_status_read(const swr_v1_coroutine_status *);
swr_v1_coroutine_dispatch_result swr_v1_coroutine_dispatch(swr_v1_coroutine_status *, uint32_t, const swr_v1_coroutine_swap_callback *, const swr_v1_coroutine_identity *, uint8_t);
/* Stage0 never mutates. Stage1 publishes only at original Native effect barrier.
 * CANCEL copy/clear and RUN current/origin/clock precede publication; TIMEOUT
 * publication precedes Native resume. No Rust borrow spans Native effects. */
swr_v1_coroutine_plan swr_v1_coroutine_status_transition(swr_v1_coroutine_status *,
    uint32_t op, uint32_t facts, uint32_t stage);
/* Typed same-layout Context cells. Raw initialization is performed only at the
 * original publication points; no reference to uninitialized fields is formed. */
typedef struct { void *pointer; } swr_v1_context_stack_cell;
typedef struct { uint32_t size; } swr_v1_context_extent;
typedef struct { uint8_t value; } swr_v1_context_completion;
typedef struct { void *pointer, *top; size_t size; uint8_t present; } swr_v1_context_stack_view;
enum { SWR_CTX_STACK_ADMIT = 0, SWR_CTX_STACK_READ = 1, SWR_CTX_STACK_TOP = 2,
       SWR_CTX_STACK_CLEAR = 3, SWR_CTX_STACK_MARK = 4, SWR_CTX_STACK_USAGE = 5 };
swr_v1_context_extent swr_v1_context_extent_new(size_t requested);
/* First constructor statement seeds completion; thread backend has null extent. */
size_t swr_v1_context_prepare(swr_v1_context_completion *, const swr_v1_context_extent *);
void swr_v1_context_finish(swr_v1_context_completion *);
uint8_t swr_v1_context_completed(const swr_v1_context_completion *);
swr_v1_context_stack_view swr_v1_context_stack_read(const swr_v1_context_stack_cell *, const swr_v1_context_extent *);
/* ADMIT follows Native allocation, CLEAR follows Native free without another
 * observation. READ/TOP refresh after Native effects; MARK uses original full
 * requested size, USAGE uses stored truncated extent. Payload marker access
 * requires the same live allocation/initialized spans as frozen marker exports.
 * No Native resource/context/function/thread effects occur inside Rust. */
swr_v1_context_stack_view swr_v1_context_stack_step(swr_v1_context_stack_cell *,
    const swr_v1_context_extent *, uint32_t operation, void *allocation, size_t requested);
/* Cursor zero-seeded, fixed operation; only external timer/cancel/timeout bits.
 * PUBLISH_CLOSED requests Native trace, then next entry publishes closed before
 * queue observation. Terminal wake must never reenter or access Channel again.
 * Allocation refusal is translated to Native bad_alloc only after return. */
swr_v1_channel_owned_action swr_v1_channel_owned_step(swr_v1_channel_owned_cursor *,
    swr_v1_channel_state *, swr_v1_channel_tokens *data,
    swr_v1_channel_tokens *producers, swr_v1_channel_tokens *consumers,
    uint32_t op, uint32_t external, void *input);
/* Whole pop/push/close, driving the step machine to completion and performing
 * each Native effect through `effects`: `query` returns fresh CANCELED/TIMEDOUT
 * bits, `suspend` enqueues the current coroutine and yields (returning
 * SWR_CH_ALLOCATION_REFUSED instead of raising), `arm_timer`/`delete_timer` drive
 * the timeout, and `resume` wakes a token. `status` 0 succeeded (`data` is the
 * popped token for a pop), negative is a SWR_CH_ERROR_*, and -5 means Native must
 * raise bad_alloc after return. close uses only `resume`. */
typedef struct {
    void *ctx;
    uint32_t (*query)(void *);
    void (*arm_timer)(void *);
    void (*delete_timer)(void *);
    int32_t (*suspend)(void *);
    void (*resume)(void *, void *);
} swr_v1_channel_effects;
typedef struct { int32_t status; void *data; } swr_v1_channel_outcome;
swr_v1_channel_outcome swr_v1_channel_pop(swr_v1_channel_state *, swr_v1_channel_tokens *data,
    swr_v1_channel_tokens *producers, swr_v1_channel_tokens *consumers,
    bool positive_timeout, const swr_v1_channel_effects *);
swr_v1_channel_outcome swr_v1_channel_push(swr_v1_channel_state *, swr_v1_channel_tokens *data,
    swr_v1_channel_tokens *producers, swr_v1_channel_tokens *consumers,
    bool positive_timeout, void *input, const swr_v1_channel_effects *);
swr_v1_channel_outcome swr_v1_channel_close(swr_v1_channel_state *, swr_v1_channel_tokens *data,
    swr_v1_channel_tokens *producers, swr_v1_channel_tokens *consumers,
    const swr_v1_channel_effects *);
/* Sole scheduler metadata in original Native constant-seeded TLS scope. */
typedef struct {
    size_t stack_size;
    long last_cid, socket_bound_cid;
    uint64_t peak_num;
    uint8_t activated;
} swr_v1_coroutine_scheduler;
swr_v1_coroutine_creation_action swr_v1_coroutine_create_step(swr_v1_coroutine_creation_cursor *, swr_v1_coroutine_scheduler *, swr_v1_coroutine_cid *, size_t);
enum { SWR_CO_STACK_MIN = 64 * 1024, SWR_CO_STACK_MAX = 16 * 1024 * 1024, SWR_CO_STACK_ALIGNMENT = 4 * 1024 };
long swr_v1_coroutine_scheduler_next_id(swr_v1_coroutine_scheduler *);
uint32_t swr_v1_coroutine_scheduler_registration(const swr_v1_coroutine_scheduler *, size_t count, uint32_t stage);
void swr_v1_coroutine_scheduler_publish_peak(swr_v1_coroutine_scheduler *, size_t count);
void swr_v1_coroutine_scheduler_set_stack_size(swr_v1_coroutine_scheduler *, size_t requested);
void swr_v1_coroutine_scheduler_set_active(swr_v1_coroutine_scheduler *, uint8_t active);
void swr_v1_coroutine_scheduler_bind_socket(swr_v1_coroutine_scheduler *, long cid);
/* Sole inline timing storage, same three-long ABI. Clocks finish before entry.
 * Switch pointers may alias; usage requires a live non-null readable record. */
typedef struct { long init_msec, switch_usec, execute_usec; } swr_v1_coroutine_timing;
swr_v1_coroutine_timing swr_v1_coroutine_timing_new(long init_msec, long now);
void swr_v1_coroutine_timing_switch(swr_v1_coroutine_timing *yielding, swr_v1_coroutine_timing *resuming, long now);
long swr_v1_coroutine_timing_usage(const swr_v1_coroutine_timing *, long now);
/* Native-owned stack bytes, no retained pointer or native effects. Only marker
 * spans are written/read; usage requires those spans already initialized. */
void swr_v1_context_stack_mark(uint8_t *stack, size_t size);
size_t swr_v1_context_stack_usage(const uint8_t *stack, size_t size);
#ifdef __cplusplus
}
static_assert(sizeof(swr_v1_coroutine_plan) == 16, "coroutine plan ABI");
static_assert(sizeof(swr_v1_channel_cursor) == 4, "channel cursor ABI");
#endif
#endif
