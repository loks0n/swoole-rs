# Reactor construction and backends

Covers `src/reactor/base.cc` construction and the poll/epoll/kqueue backends
(`src/reactor/{poll,epoll,kqueue}.cc`).

## Construction

The constructor's backend plan preserves the requested type and chooses the
compiled factory separately. AUTO keeps epoll priority, then runtime-enabled
kqueue, then poll. An explicitly requested but uncompiled type keeps its
original `type_` value while selecting the poll factory. Native observes
runtime kqueue enablement only when Rust asks at the AUTO decision point.

A zero-initialized phase requests, in order: readiness observation, field
initialization, create-hook observation/invocation, defer-end/defer-exit/idle
installation, main-thread observation/signal installation, try-exit
installation, a fresh trim main-thread observation/installation, and
default-exit installation. Native executes each action after Rust returns; the
factory switch is Native dispatch over the Rust-selected factory. No backend,
function, manager, clock or hook pointer is retained in Rust. The installed
lambda bodies themselves stay Native.

## Kernel event storage

Rust owns a fixed `Vec<MaybeUninit<T>>` of `libc::epoll_event` or
`libc::kevent`; the backend class keeps a borrowed pointer and an opaque owner.
The kernel initializes returned records. Rust neither interprets nor drops the
socket/udata tokens and never resizes the array, so Native wait counts must stay
within the construction bound.

- epoll: `epoll_create` runs before storage creation; `max_event_num` and
  `native_handle` are published after storage succeeds.
- kqueue: keeps its original publish-before-array-creation order. Its private
  pointer is now initialized, so a failed kernel create no longer reaches an
  uninitialized pointer in the destructor.
- Both destructors close the kernel handle before releasing the Rust array.

Checked layouts: macOS arm64 `kevent` 32 bytes, align 4, offsets
0/8/10/12/16/24; Linux aarch64 `epoll_event` 16 bytes, align 8, offsets 0/8.
Other targets are unqualified. The Rust vector plus owner use two allocations
where the original used one.

## Poll snapshot

`PollSnapshot` owns a bounded `Vec<libc::pollfd>` sized once at construction;
reset/push never grow or move it. Native caches a borrowed `pollfd*` and never
frees it. The original `const auto sockets = reactor_->get_sockets()` copy is
still taken before reset and marshalled in the same order. Rust stores fd values
only. Native calls `poll`, interprets the result, looks up the registry, and runs
callbacks, logging, timeout and destruction.

Both `translate_events_to_poll/from_poll` algorithms run in Rust (including
error/HUP suppression when read/write bits are set); the C++ functions are
forwarding shims. `swr_v1_reactor_poll_layout` exposes size, alignment and field
offsets for compiler comparison. Exceeding the configured limit returns failure;
Native throws `bad_alloc` after Rust returns. Negative counts keep Native
`bad_array_new_length`. No concurrent wait/reset/free is permitted.

## Registration

Rust selects poll admission, epoll control-result/cleanup/publication and
kqueue filter/result/cleanup/publication. Native keeps the single registry,
kernel calls, warnings/backtraces and map publication.

- Poll: existence is checked before capacity; removed before existence.
- Epoll: `get_events` stays Native for compatibility but forwards flag
  translation to the libc mask export (`epoll_mask`). Add publishes before its
  trace; set/delete trace before publishing. Delete calls Native
  `after_removal_failure` before passing fresh errno to Rust.
- Kqueue: read before write, partial filter effects, default read, per-filter
  deletion; fresh current events are supplied after successful effects. After
  the Native removal observer, Rust decides errno cleanup before requesting
  another event-field read.

Observation guards (applies to write/flush shims too): admission capacity is
captured before effects; no Socket fields are re-read after a full successful
send; empty/length/TLS, output-presence and writable-interest facts are read
only in the phases that need them; `close_wait` is read only after a negative
send and `send_wait` only when `close_wait` was false; the timer is inspected
only after draining; registration add/set do not read `removed`.

## Wait

`wait()` on all three backends uses a Rust state machine for
before/begin/wait/result/end/once sequencing; Native runs kernel waits,
callbacks and warnings. Warning termination returns 0 for poll and `SW_ERR` for
epoll/kqueue.

The kqueue timeout reply gives a positive millisecond timeout priority over
deferred work, keeps exact second/nanosecond arithmetic, and otherwise passes a
null timeout; Native builds the `timespec`.

The four-byte `WaitState` and `wait_step` ABI are frozen. The additive
`wait_workflow` uses effects 0..9 and requests 10 running, 11 EINTR, 12
io_uring handler, 13 once. Native supplies 0 for 11 when io_uring is not
compiled. Catch classification precedes errno; handler presence is observed only
after EINTR. Once is requested after end callbacks, then running only if needed.

## Batch decoding

A Rust cursor walks the same target C arrays the kernel filled. Rust owns record
iteration, idle/null-token skips and readiness/filter decoding. Poll keeps its
current-registry fd lookup; epoll/kqueue return opaque identity bits for Native.

The cursor POD holds next/current indices. A reply holds identity bits, fd,
readiness mask, original filter and record kind. Each call borrows only the
initialized prefix Native declares; the API bounds-checks indices against that
prefix, but Native must guarantee the prefix fits the allocation and is
initialized. The current record is decoded again after each Native effect. ONCE
removal ends the record immediately. kqueue `fill_event` is field marshalling
only; the removal decision comes from the Rust action path.

## Readiness workflow

Record consumers delegate the observation schedule and handler-result/warning
selection to Rust. `ready`/`ready_step` are unchanged. A 20-byte POD holds policy
state and scalar facts. It requests fresh batch-mask and removed facts, runs the
frozen policy, requests ONCE only when needed (including when a refreshed mask
becomes empty) and refreshes the batch before committing. Handler results are
supplied fresh; Rust picks the warning action only for negative results. Native
performs reads, handler calls, logging and deletes.

## kqueue signals

The signal record path delegates its short-circuit sequence to Rust: observe
activation, then handler presence, then whether the handler differs from
`SIG_IGN`, then request invocation, warning or completion. Each observation is
fresh and taken only where the original code read it. A zeroed 4-byte POD holds
progress; no Signal or function pointer enters Rust. The dispatcher returns
immediately after invocation/logging with no further Signal read.
