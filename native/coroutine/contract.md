# M06 coroutine core

Implements `docs/coroutine-abi-v1.md`. Selected with `SWOOLE_RS_COROUTINE`
(`--enable-swoole-rs-coroutine`); disabled selection keeps the original source
exactly. Headers: `swoole_rs_coroutine.h`, `swoole_rs_channel_tokens.h`.

| Patch | Upstream files |
| --- | --- |
| 0001-scheduler-channel-policy | `src/coroutine/base.cc`, `src/coroutine/channel.cc` |
| 0002-channel-owned-tokens | `include/swoole_coroutine_channel.h` |
| 0003-context-stack-markers | `src/coroutine/context.cc` |
| 0004-timing-header | `include/swoole_coroutine.h` |
| 0005-context-bookkeeping | `include/swoole_coroutine_context.h`, `src/coroutine/thread_context.cc` |

Rules for every entry point: Rust stores only opaque Native identities and
scalar state; it never interprets a whole Coroutine, Context, Channel or task.
Every Rust frame and borrow ends before Native callbacks, context switches,
clocks, timers, allocation, printing or destruction. Exported functions do not
call other exported functions internally; they share private kernels.
Selected builds change protected field types (layout sizes stay the same unless
stated), so selected SDK consumers must rebuild; old SDK source/binary
compatibility is not provided.

## Coroutine state transitions

`swr_v1_coroutine_transition` takes a copied operation, boolean fact mask and
Native resume code and returns a 16-byte plan by value. State `-1` and resume
code `INT32_MIN` mean "preserve". Its error values are policy results, not
Swoole error numbers; callers translate them. It never changes errno. Cancel
copies its Native function before clearing the object and does not touch the
object after invoking the copy.

The State/ResumeCode pair is one constant-seeded 8-byte C POD (align 4; state
at 0, code at 4) owned by Rust; Native keeps no mirror. Stage 0 decides without
mutation; stage 1 publishes at the original barrier: RUN after current/origin/
clock effects; cancellation after the function copy and clear; timeout before
resume; YIELD/RESUME/CLOSE before their callbacks. Post-wait timeout precedes
timer deletion, then a fresh code read checks cancellation. Coroutine stays
144 B / align 8 with unchanged member offsets.

## Identity cells

`current`, `origin`, `task` and the cancel-function pointer are
`swr_v1_coroutine_identity` cells at the original offsets. `current` keeps its
`SW_THREAD_LOCAL` scope and null seed. `swr_v1_coroutine_identity_route`:
ENTER does `origin=current` then `current=this`; LEAVE re-reads origin and
restores current. Run enters before its clock/state publication; resume enters
after the resume callback; yield and close leave after their callback/trace.
Cancellation observes admission, copies the function, clears the identity,
publishes canceled status, then returns the function's result. Pinned `gdbinit`
uses `current->cid` directly and is not updated.

## Swap callbacks and dispatch

`on_yield`, `on_resume` and `on_close` are `swr_v1_coroutine_swap_callback`
cells with their original names, TLS scope and null seed; the public
`SwapCallback` alias and setters are unchanged. C++ compilers must prove the
alias equals the C-seam function pointer type; the pointer is never converted
through an integer or `void *`. `swr_v1_coroutine_dispatch` reads the cell and
task identity, publishes the lifecycle plan and returns a plan/function/task
descriptor; Native invokes the function afterwards. Resume bailout skips the
callback/task reads; an absent function skips the task read.

## Bailout walk

`swr_v1_coroutine_bailout_step` saves current before observing the supplied
function. A null function returns the default callback effect without reading
the function or offset. After the Native `std::function` assignment succeeds,
Native passes the forward offset of the `origin` member. Rust reads only that
`repr(C)` identity cell from each allocation: two fresh parent reads per
nonterminal hop, one for the final null test. Contract: cells are live, aligned
and initialized, every reached object has the same offset, arithmetic stays in
bounds, the chain terminates, and access is serialized. The ABI cannot verify
provenance or bounds.

## Entry

`swr_v1_coroutine_entry_step` owns `coroutine::run` and C create: availability/
init admission, activate/create/wait/deactivate sequencing and Boolean versus
CID return. The run frontend always initializes; an already-available C create
skips activation/wait/deactivation. Init failure returns before activation; the
create result is saved across wait/cleanup and normalized only for the Boolean
frontend. Native keeps the raw function pointer type until the real
`Coroutine::create`, preserving `std::function` conversion timing.

## Scheduler statics

Stack size, last ID, socket-bound ID, peak count and activation form one
constant-seeded `repr(C)` record in the original global/TLS scope. Rust owns
limit/alignment, ID, registration and publication policy; Native keeps the
registry and effects. Registration reads the count twice only on the
peak-update branch; activation reads its flag separately after peak publication.

## Timing

A private inline `repr(C)` three-`long` record. Native seeds Timer milliseconds
then monotonic microseconds before Context construction and samples each clock
before calling Rust. Rust accumulates and answers elapsed-time queries,
handling the yield/resume same-record alias in the original update order.

## Context stack

The stack pointer, `uint32` extent and completion byte are inline Rust cells
with the original widths, alignment and offsets. Context is 80 B / align 8
(128 B with the thread backend; Coroutine 192 B there).

- Extent conversion stays at its field initialization after `fn` is moved.
- `swr_v1_context_prepare` raw-writes completion at the first constructor
  statement, then reads the extent for allocation; the thread backend uses a
  null extent. ADMIT writes the pointer only after allocation (original
  null-only check).
- The requested size and the stored `uint32` extent differ: `uc_stack.ss_size`
  and marker initialization use the full argument; allocation, top and query use
  the extent.
- Destruction: observe pointer, Native logging/valgrind, re-read pointer/size for
  Native free, then CLEAR writes null and reads nothing more. The getcontext-error
  free path still has no clear (upstream behavior).
- Function entry is followed by completion publication, then swap/unlock.

Stack markers: `swr_v1_context_stack_mark` writes the original magic bytes;
`swr_v1_context_stack_usage` reads only initialized marker spans, never a slice
over the uninitialized allocation. Initialization includes the sample at
`offset == size`; queries exclude it (original `<=` vs `<`). The initial 64 KiB
estimate and the doubled last changed sample (which can exceed the allocation)
are kept.

The ucontext-derived SDK fails to build under `-Werror` because of an unused
`sp` in unchanged Native code.

## Channel

`swr_v1_channel_step` borrows an aligned caller-local four-byte cursor for one
call (null is invalid; aliasing cannot be checked). Operations: push 0, pop 1,
close 2. Facts are copied fresh on each return. Actions: timer, queue transfer,
yield, wake or closed publication; negative errors match Channel errors. Phase
6 is terminal; invalid operation/phase returns -4. The operation is fixed for a
cursor's lifetime. Rust owns wait/fairness/error precedence and
producer-before-consumer close order. A Native timer delete completes before
cancellation state is re-read; a timed-out yield returns before deleting its
expired timer. Successes leave `error_` untouched.

A push/pop WAKE is terminal: Native returns the captured result right after
resume without touching the Channel, because the resumed waiter may delete it.
Close wakes are nonterminal; the Channel must stay alive through the next queue
check.

Storage: the data FIFO and both waiter lists are three opaque Rust handles, each
one `VecDeque` of pointer identities (null payloads allowed; front status
distinguishes empty). Construction, clone and growth are fallible; Native throws
`std::bad_alloc` after return. Implicit copy construction/assignment copy
identities into independent queues. Capacity/closed/error live in one
initialized POD prefix (16 B, align 8); selected Channel is 40 B with handles at
16/24/32 (Native 112 B). Capacity 0 is not normalized, success keeps sticky
errors, and closing an already-closed channel keeps its previous error.

`swr_v1_channel_owned_step` runs the same phase/fairness kernel directly on the
Rust queues; only fresh timer/cancel/timeout flags cross in. Close returns
PUBLISH_CLOSED first; Native traces before the next call publishes closure.
Rust removes a waiter before returning its identity. Allocation refusal returns
-5 at the original transfer point. `swr_v1_channel_pop_data` removes an optional
token in one call (a stored null still counts as data).

`swr_v1_channel_waiter`: enqueue and pop use the producer queue only for role 1;
removal uses the consumer queue only for role 2 (preserving the original
asymmetric else branches). Removal erases all equal identities. `Channel::yield`
enqueues before the trace and cancel-closure construction; cancellation removes
before resume. The timer callback publishes `msg.error=true`, then
`msg.timer=nullptr`, removes, then re-reads `msg.co` for resume.

## Coroutine map

`Coroutine::coroutines` is upstream's `std::unordered_map<long, Coroutine *>`.
Its iteration order is unspecified upstream and differs between standard
libraries, so no Rust replica of one library's order is kept (#357).
