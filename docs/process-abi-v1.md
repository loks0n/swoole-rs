# Workers, processes and IPC boundary (M08)

Feature value 524288 (`--module process`). Upstream targets:
`src/server/{worker,task_worker,process,manager,reactor_process}.cc` and
`src/os/{process_pool,pipe,signal,wait}.cc`. Public Server/Factory/Worker/
ProcessPool/ReloadTask/Signal/EventData layouts and PHP bindings are unchanged.
Follows the [policy/effect split](abi-v1.md#policyeffect-split).

Rust implements state transitions, worker/task selection, progress/retry/error,
reload and exit policy. Native code executes syscalls, atomic read-modify-writes
(not split into separate read and write decisions), queue/container mutation,
allocation, timer/reactor operations, context switches, callbacks, exceptions and
Zend escapes. Signedness, width, casts, wrapping, errno and last_error match
upstream. Worker CPU pinning is the exception: Rust makes its affinity syscalls.

There is one native store each for workers, PIDs, reload snapshots, task results,
connections/sessions, signals, waiters and child status, and one IPC transport.
No Rust registry, scheduler, signal queue, async pool, message reassembler,
runtime or background thread. PID, worker ID, session ID and fd are distinct
identities; stale ones never match a new occupant.

- Callbacks may change settings or maps, close connections, dispatch again or
  destroy an event/coroutine; facts are refreshed at each original observation
  point.
- `fork` and `fork_exec` run natively with no Rust frame across the parent/child
  split. `fork_exec` failure returns pid 0 as upstream. No inherited Rust mutex
  or global state.
- Signal handlers stay async-signal-safe: no Rust allocation, I/O, formatting,
  mutex, callback or unwinding in a signal frame. Saved errno, masking and
  reentrant delivery order are native.

Ordering kept from upstream:

- ProcessPool create/start partial resource publication; `onStart` before spawn;
  old PID erased before fork.
- Manager handles messages before timers; ProcessPool handles timers before
  messages.
- Reload snapshots with old/new worker overlap; abnormal-exit callback before
  respawn; timer kill before clear.
- Upstream's final wait loop breaks unconditionally on its first iteration, so
  it does not guarantee all children are reaped.

Original inventory: 287 Process/ProcessPool/Server PHPTs; corpus
`10-task-workers`. Tests must use isolated process groups, private files, IPC and
ports, and must not kill by name.
