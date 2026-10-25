# OS support and async worker boundary (M20)

Feature value 131072 (`--module ossupport`). Upstream targets:
`src/os/{async_thread,base,file,msg_queue,sendfile,unix_socket}.cc`.
`src/os/timer.cc` belongs to M03. Follows the
[policy/effect split](abi-v1.md#policyeffect-split).

Rust decides worker sizing, scheduling, event results, lifecycle and file/IPC
progress. Native code runs every syscall, allocation, thread/mutex/condition/pipe
operation, log and callback. The process-wide shared pool, thread-local
AsyncThreads, pipe and AsyncEvent custody stay native.

## Async thread pool

- Scheduling uses the old queue state before the new task is published.
- Default worker count is `cpu * 8` even when an explicit core count is larger.
- `max_idle_time` is cast to `long` before multiplying by microseconds.
- A missing handler takes precedence over the canceled status.
- A failed completion write deletes the event without counting a delivery.
- Idle retirement keeps its compensating task counter.
- Callbacks are invoked natively, then the thread-local pool is reacquired for
  the decrement/delete. Destruction drops local pool custody before shared
  shutdown and pipe release.
- With the module selected, the private EventQueue `std::queue` is one Rust
  `VecDeque` of opaque event tokens, used only under the existing `event_mutex`.
  Rust never reads token fields. Allocation failure returns a status; native
  throws afterwards. The backing store is dropped after native shutdown/join and
  never frees the `AsyncEvent` payloads.

Known gap: the native `uint8` `canceled` field is read across threads without
proven synchronization.

## Files, message queues, sendfile

- `file_put_contents` treats a partial positive write as success. Append mode
  uses `write`; non-append uses `pwrite` at offset 0.
- `read_line` includes the NUL/newline as upstream; a full chunk skips one byte
  at `offset + read_bytes + 1`.
- Close invalidates the fd before the syscall and never retries on `EINTR`.
- `File::exists` checks `R_OK`; `file_exists` checks `F_OK`.
- MsgQueue: one kernel id, automatic removal only for private queues, default
  mode `0666` for out-of-range permissions, `set_blocking` changes only flags,
  `EINTR` retry only on push. Tests use a private IPC namespace or a reserved key.
- Sendfile keeps separate Linux, Darwin/BSD and fallback offset/result/retry
  rules, including progress reported before `EINTR`.
- Entropy, daemon, identity and resolver hooks run natively.
