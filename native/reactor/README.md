# M05 reactor and stream

Opt-in Rust policy for the Swoole reactor backends, callbacks, Socket I/O and
output queues. The frozen ABI is `docs/reactor-abi-v1.md`; the module-local
headers are `swoole_rs_reactor.h`, `swoole_rs_reactor_defer.h` and
`swoole_rs_reactor_sockets.h`. Rust sources are in `crates/reactor/src/`.

General rule for every seam: Rust receives copied scalar facts and returns a
decision. Native code then performs the syscall, callback, warning, allocation,
exception or Zend effect. No Rust frame or borrow spans a Native effect, and
Rust never dereferences, drops or invokes a Native Socket/callback token.
Warnings stay in their original Native method so `__SW_FUNC__` is unchanged.

## Patched upstream files

| Patch | Upstream files |
| --- | --- |
| 0001-readiness-policy | `include/swoole_reactor.h`, `src/reactor/{poll,epoll,kqueue}.cc` |
| 0002-write-policy | `src/reactor/base.cc` |
| 0003-stream-framing | `src/network/stream.cc` |
| 0004-socket-output | `src/network/socket.cc` |
| 0005-iov-owned | `include/swoole_socket.h` |
| 0006-socket-registry-admin | `ext-src/swoole_admin_server.cc` |
| 0007-server-buffer-typed | `src/server/base.cc`, `src/server/reactor_thread.cc` |

The optional M15 half-close patches apply first when requested and stay
byte-identical; the M05 hunks continue after their prefixes.

## Optional storage capabilities (all OFF by default)

| Macro / configure option | Effect when 1 |
| --- | --- |
| `SWOOLE_RS_REACTOR_IOV_OWNED` / `--enable-swoole-rs-reactor-iov-owned` | Rust owns IOVector arrays ([socket-io.md](socket-io.md)) |
| `SWOOLE_RS_REACTOR_DEFER_OWNED` / `--enable-swoole-rs-reactor-defer-owned` | Rust FIFO for `defer_tasks` and `destroy_callbacks` ([callbacks.md](callbacks.md)) |
| `SWOOLE_RS_REACTOR_SOCKETS_OWNED` / `--enable-swoole-rs-reactor-sockets-owned` | Rust socket registry ([socket-registry.md](socket-registry.md)) |
| `SWOOLE_RS_BUFFER_TYPED` / `--enable-swoole-rs-buffer-typed` | Server callers use the typed Rust Buffer queue ([output.md](output.md)) |

The reactor capabilities require `SWOOLE_RS_REACTOR` (`--enable-swoole-rs-reactor`). Each changes the selected private class
layout, so every selected SDK consumer must rebuild.

## Contents

- [backend.md](backend.md): construction, poll/epoll/kqueue storage,
  registration, wait, batch decoding, readiness and signals.
- [callbacks.md](callbacks.md): ordered end/exit callbacks, handlers, builtin
  defer/idle/exit scheduling, deferred queue ownership.
- [socket-registry.md](socket-registry.md): Rust-owned fd→Socket registry,
  iteration order and iterators.
- [socket-io.md](socket-io.md): ordinary Socket I/O, options, connect,
  datagrams, blocking calls and IOVector.
- [output.md](output.md): Socket output queue progression, writable/drain,
  `Reactor::write_func`, typed server Buffer consumers.
- [production.md](production.md): loaded-PHP consumer profiles.

## Checks

Build the archive, then run a facade gate against the pinned source:

```sh
python3 tools/shared_cache.py -- cargo build --locked --offline --release -p swoole-rs-reactor --target-dir PRIVATE_TARGET
python3 tests/modules/reactor/builtins.py --source PINNED --archive PRIVATE_TARGET/release/libswoole_rs_reactor.a --sanitize --report UNIQUE.json
```

Other gates under `tests/modules/reactor/` take the same
`--source/--archive/--report [--sanitize]` arguments: `backend_storage.py`,
`poll_snapshot.py`, `registration.py`, `wait.py`, `batch.py` (no `--source`),
`initialize.py`, `callbacks.py`, `callback_queues.py`, `handlers.py`,
`flush.py`, `write_positive.py [--workflow]`, `write_arguments.py`,
`iov_owned.py`, `sockets.py [--order-model] [--standard]`,
`socket_iterators.py` and `output.py` with one profile flag (`--blocking`,
`--iov-progress`, `--ordinary-io`, `--socket-policy`, `--fd-options`,
`--socket-options`, `--forwarding`, `--datagram`, `--connect`).
`rust_asan.py` runs filtered Rust ASan units with `--snapshot-only`,
`--flush-only`, `--backend-only`, `--registration-only` or `--wait-only`.

These gates extract the complete original and selected method bodies and run
them against Native effect facades with positive inputs only. Error,
interruption, allocation-failure, reentry and lifetime paths are not executed,
and the unfiltered Rust-ASan entrypoint refuses to run. Mixed Rust/Native ASan
linking fails on macOS (runtime version symbol mismatch); it works on Linux.
