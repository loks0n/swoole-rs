# Worker termination and in-flight responses (open)

When an event worker dies while it owns a suspended HTTP response, the client
connection stays open with no bytes and no EOF. `worker_terminal.py` (flags
`--probe-worker-kill`, `--probe-retiring-worker-kill`, `--probe-worker-drain`,
`--probe-worker-exit-zero`) signals only a worker verified to be in the isolated
test server's process group.

| Scenario | Result on macOS and Linux |
| --- | --- |
| normal response | passes |
| graceful drain: `Server::stop(0)` with default async reload; old response held by a file barrier | replacement serves new work and the idle TCP session; releasing the barrier delivers the old response |
| current worker SIGKILL | replacement serves; idle keep-alive connection still works; in-flight client gets nothing within 1 s |
| retiring (detached) worker SIGKILL | same as above |
| `_exit(0)` via PHP FFI in the owning worker | same as above |

"Fails" means no response/EOF within the one-second observation, not a
permanent hang.

## Upstream control flow

| Event | Path | Requirement |
| --- | --- | --- |
| graceful STOP | `worker.cc` sends STOP with PID/id; `manager.cc` spawns a replacement and puts the old PID in `detached_processes` | old response may stay valid after the replacement starts |
| current worker exit | `restart_worker_process` finds the Worker by PID, then checks exit status | in-flight work must be cancelled without dropping idle connections |
| detached worker exit | PID lookup fails; the detached PID is erased and the function returns before the exit-status callback | the worker-error callback alone cannot cover this |

`worker-terminal-current-source.json` confirms the integrated M15/M08 overlays
leave these six retirement/exit/lookup bodies and the STOP-consumption block
byte-identical to upstream.

## Required semantics for a fix

- Cancellation must come from actual reaping of an event-worker generation,
  including status-0 exits and detached retirees, not the nonzero-only
  worker-error callback.
- Replacement or STOP alone must not cancel the old generation.
- Settlement must identify session, request and worker generation; forced
  cancellation must keep unrelated idle connections and reject late completion
  after session reuse.
- The reactor must define ordering between the terminal notification and worker
  response messages already sent; separate IPC streams imply no order.

See also `docs/http-response-lifetime.md`.
