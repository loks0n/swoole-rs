# M29 PHP coroutine frontend

Boundary: `docs/phpcoroutines-boundary.md`. Header: `swoole_rs_phpcoroutines.h`
(`phpcoroutines_registration.h` for startup). Selected with
`--enable-swoole-rs-phpcoroutines`.

| Patch | Upstream files |
| --- | --- |
| 0001-scheduler-queue | `ext-src/swoole_coroutine_scheduler.cc` |
| 0002-user-yield-registry | `ext-src/swoole_coroutine.cc` |
| 0003-system-file-admission | `ext-src/swoole_coroutine_system.cc` |
| 0004-deferred-context-header | `ext-src/php_swoole_coroutine.h` |

Rules for every entry point: no Zend value, PHP object, context or callable
pointer enters Rust; Rust holds opaque tokens and scalar facts only. Native code
performs every Zend conversion, warning, allocation, refcount, callback, yield/
resume and bailout after Rust returns, and no Rust frame or borrow spans them.
Most entry points are cursors: a zeroed Native stack POD that returns one
action or observation request per call. Invalid cursors are outside the
contract. Rust containers allocate differently from the C++ ones they replace;
allocation counts, capacity limits and exact exception types (e.g. length
errors) are not matched.

## Containers

All containers own metadata only: tokens are never validated, dereferenced,
refcounted or freed by Rust. Handles need serial exclusive access from their
owner, non-aliasing output and exactly one drop. Constructors and pushes use
fallible `try_new`/`try_push`/`try_put`: zero admission makes Native throw
`std::bad_alloc` after return. Reserve completes before a token is published.
The older allocation-bearing exports remain for compatibility but are not used
by Native callers.

**Scheduler queue** (`scheduler_*`): one `VecDeque` per SchedulerObject of task
tokens with signed repetition counts. Native persists the callable/params before
`push`. `pop` removes a record before returning its token and `max(count, 0)`
repetitions (the iterations of the original `for (i=0; i<count; i++)`); empty
pop leaves output untouched and returns 0. `drop` consumes the drained queue;
Native drains payloads first in original cache/parameter/free order. Object
`list/started/std` offsets, size and alignment are unchanged; SchedulerTask's
count field is removed.

**User-yield registry** (`yield_registry_put/take/erase/drop`): kept in the
original `static SW_THREAD_LOCAL` owner (process-global without `SW_THREAD`,
per-thread with it). The C++ owner holds an opaque handle; the first put lazily
allocates the Rust map and publishes it only after the first successful insert.
Put replaces the same signed key; take removes before returning a found flag and
token (zero is a valid token); a missing take leaves output untouched; erase is
idempotent. The older thread-local `yield_put/take/erase` exports remain.

**Autoload waiters**: a Native stack RAII wrapper owns a `VecDeque` of waiter
tokens, replacing the local `std::queue`. Pop removes before Native writes the
class result or resumes. AutoloadQueue keeps its two pointer fields, size,
alignment and queue offset.

**Deferred callbacks** (`defer_*`): `PHPContext.defer_tasks` points to an
opaque owner with a LIFO `Vec`; the field type changes but every context offset,
size and alignment is unchanged. `create_context` publishes null; the first
defer constructs and publishes the owner before push. `main_func` captures the
same owner before draining; each pop removes before the callback runs, and new
insertions during draining are seen. `destroy_context` re-reads
`ctx->defer_tasks` each iteration and keeps cache-discard/free order.

## Policy cursors

- **options**: lookup/convert/apply/merge actions with static Rust key bytes.
  Primary `max_coro_num` and `c_stack_size` suppress their aliases only when
  found and non-null. Nonpositive maximum selects the Native default. The final
  options-existence fact is refreshed after resolver effects before choosing
  merge or duplicate.
- **create**: requests limit, handler-validity, handler-type, activation facts
  in that order (no function-cache read before the limit decision, no type read
  before presence). After activation the next step requests create without
  rechecking the limit. Count/config/type constants keep their unsigned widths.
- **configure** (`Scheduler::set`): global options, coroutine options, non-null
  DNS expire/capacity, then presence-only `exit_condition` (explicit null
  counts). Old-cache presence before release; successful creation publishes the
  callback pointer before reactor presence is read. Invalid creation
  removes/clears only when a reactor exists; otherwise the previous global
  callback pointer stays.
- **scheduler control**: exit-callback error/result selection, resolver
  classification, resolver-before-cache cleanup and options admission. Resolver
  `private_data` is re-read for free after Native destruction; cache presence is
  read after traversal; clear follows free. Success/type/resolver constants are
  passed in, not hardcoded.
- **activation**: already-activated returns before any lookup. Library presence
  before truth conversion; false/absent loads the library. Reactor admission
  precedes interrupt binding. Global preemption=true suppresses the local read.
  Main-thread status gates hook-flag inspection and hook/unsafe-function binding.
  Final order: destroy registration, core activation, yield/resume/close callback
  registration, `activated=true`.
- **autoload_policy**: one current lookup; missing context goes straight to
  the original classloader. Coroutine callers delete `in_autoload` before
  table-presence, optional init and lookup. A found queue is captured once; a
  recursive owner returns null, otherwise the waiter branch uses that queue.
- **stats**: ordered field catalog. Absent async workers emit three zero fields
  without reading counters; absent/disabled io_uring emits no ring fields; the
  ring pointer is read at its original late point. `zend_long` truncation of
  fractional occupancy is kept.
- **system_file**: from path-nonempty, signed flags and Native platform
  constants, selects admission, lock bits and append vs truncate. No libc crate
  or assumed platform values.
- **system_sleep**: `seconds < minimum`, including unordered operands.
- **system_address**: empty-name/family admission for both hostname frontends.
- **system_complete**: sleep/read/write/hostname result admission and addrinfo
  array / statvfs field publication order (11 stat fields). The statvfs return
  code is still ignored, as upstream.
- **context_route**: active admission, parent current/by-id lookup and
  main-context fallback; C++ returns the Native pointer.
- **stack_step**: effective id, current/saved page, existence, walk and `size_t`
  wrapping sum; Native reads Zend page fields and computes
  `(ptr difference) * sizeof(zval)`. Final `size_t`→`ssize_t` stays in C++.
- **scheduler_policy**: disabled-clock short circuit, strict
  `elapsed > MAX_EXEC_MSEC`, enable/disable admission, interrupt clock admission.
  Equivalence only for non-overflowing `int64` subtraction.
- **context_query** (`getContext`): uses raw `Coroutine::get_task_by_cid` even
  for -1 (no main-context substitution). Object facts are re-read after each
  plan; `object_init_ex`, field publication, `GC_ADDREF`, `RETURN_OBJ` keep their
  order.
- **trace** (`getBackTrace`, `sw_php_print_backtrace`): zero-id short circuit,
  current-id equality, lookup, executor switch/trace/restore, self-print skip
  count. Native writes `EG(current_execute_data)` and restores it.
- **bootstrap**: the three MINIT sequences: class/alias/constant/property names,
  class/handler/fixup order, per-class short-name admission, one CLI read, and
  the PHP-version exit-opcode gate. The helper initializes the class entry, then
  reads the parent slot.
- **cancel/timeout**: throw/nonthrow lookup, missing/already-canceled outcomes,
  exception-chain admission, executor save/file/line/restore, ignored vs returned
  core cancel result. Timeout keeps `(long) timeout * 1000` (subsecond values
  become 0 ms); parity only for finite values representable as `long` without
  overflow. A timeout callback deletes its node before a fresh context lookup.

## PHPContext metadata cells

Seven primitive PHPContext fields are module-local C cells owned logically by
Rust: silence, scheduler admission, original/temporary error masks, fiber init
notification, parent CID and last scheduled clock. Names, widths, alignment and
all offsets are unchanged. Native passes cell addresses only. Ordering: silence
publication precedes the fresh error-mask read; save writes the temporary mask
before reading the original; scheduling short-circuits before the clock and
reads `last_msec` after the Native clock returns; lineage publishes after the
core query; the fiber byte publishes after fresh status. Native synchronization
rules still apply.
