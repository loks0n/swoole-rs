# Worker, task and reload transitions v1

Opt-in feature bit 524288 (`process`). ABI: `docs/process-abi-v1.md` and
`swoole_rs_process.h`. Callers are in `src/server/worker.cc`,
`src/server/task_worker.cc`, `src/server/manager.cc` and `src/os/process_pool.cc`.

Rust decides worker-exit observation and timeout plans, discard triage,
task-kind/finish diagnostic/result-flag precedence, ordinary manager reload
selection and stale-PID/reload-kill result actions. All APIs take copied
bool/int facts and return POD/scalars (CPU pinning and task files also take
native pointers). No allocator, callback, borrow,
registry or native handle enters Rust. Server/Worker/ProcessPool/ReloadTask
state, counters, maps, PID snapshot and kill queue stay native, as do logging,
signals, syscalls, timers, reactor, callbacks, fork, atomics and coroutines,
which run after Rust returns.

- WorkerExit observes `if_exit` before callback presence, publishes its local
  `called` flag before the native callback, then observes reactor/settings/clock
  again. The clock is not sampled before the callback or when the reactor can
  exit. Remaining seconds keep native `int` narrowing; positive `remaining*1000`
  outside `int` range is undefined input. Native timeout is written only when the
  original comparison required it. No Rust frame spans the callback.
- Task shutdown keeps its early return without idle publication; only ordinary
  tasks increment request accounting. Finish: `PIPE_MESSAGE` precedes `NOREPLY`.
  Task packing stays native before callback/coroutine flag selection, and
  `CALLBACK` wins. The original `latest_task == nullptr` invalid context remains
  a native gap.
- Worker discard keeps null / closed / disable-notify precedence; the warning is
  native.
- Manager reload selection runs only in the ordinary wait loop, after the
  original message/timer/signal dispatch. `Server::reload` and signal frames stay
  native. All-worker reload precedes task-only reload.
- Reload kill actions consume a fresh native kill result/errno. ESRCH/ECHILD
  erase-and-continue only for `kill_one`; `kill_all` keeps its map. EPERM/other
  failures warn then stop that attempt. Worker iteration, kill queue, timer
  kill-before-clear and callback order are unchanged.
- Worker CPU pinning (`Worker_set_cpu_affinity`, Linux) is one Rust operation:
  read the process's affinity, keep `cpu_affinity_available`, pick the
  `worker_id % count`-th CPU and pin the thread (thread mode) or process. Native
  sets errno from the outcome and logs upstream's warnings.
- A task's temporary file (`Server::task_unpack`) is read in Rust: open, pread
  `length` bytes retrying EINTR/EAGAIN, close, unlink unless `SW_TASK_PEEK`.
  Native sizes the buffer first (upstream did so after a successful open), then
  logs the open/pread warnings and builds the packet.
- The signal table (`src/os/signal.cc`) is Rust's `swr_v1_signals`, laid out as
  `swoole::Signal` so the native signalfd and kqueue paths (and kqueue's udata)
  still use it. Rust registers handlers through sigaction, runs the deferred and
  immediate async handlers (atomic stores; the immediate one calls
  `swoole_signal_callback` in the signal frame as upstream), dispatches marked
  signals and blocks/unblocks every signal. Native keeps the warnings and calls
  the looked-up handler. Dispatch's callback may run PHP; no Rust value with a
  destructor is live across it. Upstream's `pthread_sigmask(...) < 0` check never
  held, so blocking all signals has no warning.

`python3 tests/modules/process/gate.py` builds the crate and runs the C++
differential under ASan/UBSan; `--archive ARCHIVE` tests an existing archive.

Not converted: the rest of startup/fork/worker/task/reload/exit/IPC/signal/wait
lifecycle.
