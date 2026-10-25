# PHP Event frontend ABI

Opt-in feature bit 67108864 (`phpevents`). Header: `swoole_rs_phpevents.h`.
Patched upstream file: `ext-src/swoole_event.cc`. Public PHP/C++ signatures,
method tables, stubs and arginfo are unchanged.

Common rules: planners take independent aligned `uint32_t` phase storage
initialized to 0, copied scalar inputs, and return `uint32_t` action tags equal to
the header enums. Each native operation runs after Rust returns; the caller then
supplies a fresh observation. No callback, Zend frame, stream, native object
pointer, GC, destructor, bailout or yield crosses Rust. Invalid/null phase
storage returns Error/False; storage lifetime and aliasing are the caller's
responsibility.

## Aliases

`SwrPhpEventAlias` is a C-layout tuple of two immutable NUL-terminated static
names and their `size_t` lengths (excluding NUL). Indexes 0..10 follow native
registration order. Index 11+ or null output returns 0 without writing. Native
keeps arginfo/class/function-table registration.

## Descriptor conversion (`fd`, `stream`)

Inputs: kind resource = 0, long = 1, object = 2, other = 3; socket capability
0/1. Stream cast observation uses Zend SUCCESS = 0; fd-read observations are
signed descriptors; other observations are booleans. Class-check order:
coroutine socket, client, process, optional PHP socket. Property reads and
presence/type checks are lazy. Native keeps signed descriptor narrowing. The
scalar-long and stream paths reject negative descriptors; object properties keep
their original unfiltered return. For streams, native initializes async = 0,
supplies resource/socket capability, and checks wrapper identity only after a
successful non-negative cast. The optional native socket fallback keeps its
unfiltered descriptor and async = 1.

## Registry

`SwrPhpEventRegistry` is the single descriptor -> opaque address map (there is no
native shadow map). A native private owner starts with null state, so queries
and erase on an empty registry allocate nothing; the first insert creates the
`HashMap` (`BuildHasherDefault<DefaultHasher>`, no `RandomState` entropy).
`contains`/`get`/`insert`/`try_insert`/`erase` follow native `unordered_map`
semantics, including replacement and zero-valued presence. Values are
`uintptr_t` scalars never dereferenced or released by Rust. `Event.add`
publishes through it; `get_socket` and `del` use it too. `registry_drop` consumes
the handle and frees only Rust storage; native discards the handle afterwards.
Access to one handle must be serialized. Iteration order is not exposed.

## Operations

- `add`: starts after native argument parsing, reactor check and descriptor
  conversion. READ = 512, WRITE = 1024, SUCCESS = 0 are compile-time checked.
  Duplicate lookup precedes mask validation. Callback construction precedes
  native allocation, reference retention, socket construction/non-blocking setup
  and the backend call. Publication only after backend success. Native keeps
  EventObject, callbacks and Socket.
- `update` / `update_owned`: after native reactor/argument/descriptor/registry
  checks and payload lookup, orders both callback constructors, lazy new/old
  observations, deferral/slot assignment, required-callback validation and
  backend result. `update_owned` internalizes new/old presence, required-slot
  checks and publication against the callback pair: native constructs both
  candidates in order, defers the returned old snapshot, then re-enters Rust to
  publish the replacement before observing the other slot.
- `query` (isset): lazy reactor check, parser, descriptor conversion, registry
  lookup, removed flag, then mask. No parser runs without a reactor, no lookup
  follows a failed conversion, and no mask is read after removed = true. Native
  parser failure returns immediately.
- `write`: validates length, then lazy descriptor/map lookup, reactor readiness
  and the backend result. Payload bytes never enter Rust.
- `delete`: original readiness/parser/fd/lookup sequence, then native
  deferral/backend/erase/invalidate/free. The backend status is kept through
  cleanup and decides the final boolean even on backend failure.
- `cycle`: after native arguments and reactor setup, selects future/idle slot and
  keeps null/check/defer/clear/create/assign order. Native owns slots and
  callables.
- `dispatch`: modes readable = 0, writable = 1, defer = 2, cycle = 3. Result
  handling begins after native `function::call` returns (which does not mean any
  asynchronous lifetime has ended). Invocation, warnings, slot clear, deferral,
  backend deletion and callable destruction stay native.

## Callback identity pair

EventObject keeps two pointer-sized/aligned `SwrPhpEventCallback` cells with the
original field names; every offset/size/alignment is asserted against the
original layout. Rust owns only their opaque integer identities; native owns
Callable payloads, Zend refcounts/GC, allocations, zsocket, Reactor and Socket.

`callbacks(SEED)` writes both cells at the original assignment point, after
native reference retention. READ/WRITE return the invocation identity. FREE
phase 0 returns the readable identity for native delete; phase 1 reads the
writable cell after that destructor and returns the final action. Slots are never
cleared by Rust. Native then destroys zsocket and calls `efree`.

## Reactor admission, handlers and loop

- `reactor_init`: CLI/server/process admission, lazy reactor creation,
  shutdown-function registration order and user exit-condition setup. Task
  coroutine capability is observed only for task workers, manager only after
  that guard, and exit-condition reads only with a freshly observed reactor.
- `handlers`: all-or-none publication of the three handlers after reactor
  readiness, in read/write/error order.
- `loop`: modes WAIT = 0, EXIT = 1, DISPATCH = 2, RSHUTDOWN = 3. Covers lazy
  fatal/reactor/coroutine/if-exit/bailout routing and the original
  wait/cleanup/timer/once order. Native `zend_try`/`end_try` still surround
  rshutdown. The shutdown wrapper still calls core wait when bailout is true, only
  omitting the deprecation warning. Native captures/clears the shutdown flag at
  the original point; Rust keeps only the copied restore boolean and requests the
  native OR after wait/error handling.

Still native: callback payloads, error handlers, retirement, shutdown, deferred
execution, single-call wrappers and effect-only socket/defer/error handling.
