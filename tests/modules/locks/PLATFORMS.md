# Locks platform boundary

Runtime validation covers macOS and Linux only. The Rust crate and the C header
`native/locks/swoole_rs_locks.h` reject every other target, including Android
(despite `__linux__`) and Apple mobile targets (despite `__APPLE__`), matching
Rust `target_os`. The upstream fallback does not compile the optional module.

Upstream `config.m4` probes pthread capabilities independently of the OS:
`HAVE_RWLOCK`, `HAVE_SPINLOCK`, `HAVE_MUTEX_TIMEDLOCK`,
`HAVE_RWLOCK_TIMEDRDLOCK`, `HAVE_RWLOCK_TIMEDWRLOCK` and
`HAVE_PTHREAD_BARRIER`. Several Rust paths are Linux-only, so a new platform
could otherwise compile with native probes selecting capabilities Rust lacks:

| Path | Rust implementation | Needed before adding a platform |
| --- | --- | --- |
| Mutex/RW storage and pshared attributes | Host-libc opaque types | Native geometry, alignment, pshared/error/destruction ordering |
| Timed mutex/RW | Linux-only, capability bits from native configure | Native timed API selection and deadline/error behaviour |
| Spin lock | Linux-only | Storage for a non-Linux `HAVE_SPINLOCK` configuration |
| Native pthread barriers | Linux-only; other targets return ENOTSUP | Barrier geometry, attributes and wait return values |
| Fallback barrier/atomic polling | macOS/Linux | Fences, word geometry, timeout/fork behaviour |
| Futex | Linux-only plus native `HAVE_FUTEX` | No syscall inferred on other OSes |
| Coroutine token policy | Copied cookies/CID, aligned atomic words | Scheduler/lifetime/atomic checks |

`platforms.py` compiles the header as C11 and C++14 on the host and checks the
synthetic FreeBSD/Android (and Apple mobile on macOS) macro sets hit the guard
error. This is a compiler-diagnostic check only; it does not compile foreign
pthread headers or run foreign code.

```sh
python3 tests/modules/locks/platforms.py --source target/upstream/src \
  --output target/reports/locks-platforms.json
```

Adding a platform needs its configured native and Rust toolchains, pthread
layouts and capabilities, the original lock/atomic/PHP tests, and matching
spin/barrier/timed paths (or the native configure-selected fallback) before
either guard is removed.
