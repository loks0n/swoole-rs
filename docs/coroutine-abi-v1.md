# Coroutine scheduler and channel boundary (M06)

Feature value 32768 (`--module coroutine`). Upstream targets:
`src/coroutine/{base,context,thread_context,channel}.cc` and their headers.
Follows the [policy/effect split](abi-v1.md#policyeffect-split).

Rust owns transition, fairness and error-order policy through a caller-local POD
cursor and typed next actions. The native Coroutine registry, public fields and
stack `TimeoutMessage` stay authoritative. No second executor, registry or timer
queue. Context switches, timer operations, callbacks, container changes,
allocation, diagnostics and unwinding run natively after Rust returns; Rust has
returned before `swap_in`/`swap_out`, bailout, `on_resume`/`on_yield`/`on_close`
and waking channel waiters.

Sequence points kept exactly:

- `run` saves the CID before possible synchronous deletion.
- `resume` runs its callback before changing current/origin.
- `yield` publishes `WAITING`/`RC_OK` before its callback.
- `cancel` copies the native function before clearing it, sets `RC_CANCELED`
  before invoking it, and does not touch the coroutine afterwards.
- `close` calls `on_close` before registry removal, current restore and delete.
- `SW_CORO_BAILOUT_EXIT_CODE` is used by name.

Channel:

- Fairness includes older producers and consumers, not just occupancy.
- A waiter is removed before it is resumed. Close publishes closed, wakes
  producers then consumers, rereading queues after each resume.
- Timeout callbacks set the stack message error, clear the timer and remove all
  matching entries before resume. After a wait, the timer is deleted before
  checking cancellation, timeout and close; cancellation wins.
- Pop may drain buffered data after close.
- With the module selected, the data FIFO and both waiter lists are three
  native-owned opaque Rust `VecDeque` handles of tokens. Rust never dereferences
  or frees payloads. Allocation is fallible; native raises `bad_alloc`. This
  changes the Channel class layout.

`context.cc`: stack marker initialization and stack-usage sampling are in Rust
(original marker bytes and placement; `<=` on init versus `<` on query). Stack
allocation, page protection, valgrind registration and the context-switch ABI are
native. Rust only touches bounded native-owned marker spans.

Execution-time accounting (`seed`, `get_init_msec`, `get_execute_usec`,
`calc_execute_usec` and the inline three-`long` timing record) is in Rust; clocks
are read natively in the original order.

Not validated: `SW_USE_THREAD_CONTEXT` (its cross-owner `std::mutex` hand-off is
not a valid Rust ownership model) and macOS ucontext. Original inventory: 130
coroutine, 44 channel and 27 scheduler PHPTs.
