# Locks validation

Opt-in Rust implementations (feature bit 1024) cover mutex, reader/writer,
spin, barrier and coroutine-lock policy. PHP Lock, Thread Lock, Atomic/Long and
Thread Atomic/Long keep their native Zend facades and call Rust through the
real classes and atomic exports. See
[native/locks/contract.md](../../../native/locks/contract.md) for geometry,
ownership, timeout, ordering, fork and coroutine contracts, and
[PLATFORMS.md](PLATFORMS.md) for the macOS/Linux platform guard.

`overlay.py` generates the patched lock sources from the pinned upstream; run it
directly to rewrite `migration/patches/locks/`.

```sh
python3 tools/build_hybrid.py --module locks --dev --jobs 2
python3 tests/modules/locks/gate.py --source target/upstream/src \
  --archive target/release/libswoole_rs_ffi.a --sanitize
python3 tests/modules/locks/upstream.py --source target/upstream/src \
  --engine upstream=target/upstream/src/modules/swoole.so \
  --engine rust=target/hybrid/dev-rust-locks/modules/swoole.so
```

## Registered gates

- `gate.py --source S --archive A [--sanitize] [--rust-asan] [--output R]`
  (`locks-native`): compiles the pinned pthread bodies and the Rust overlay
  facades into one driver (`gate.cc`) and compares thread/fork/RW/timeout/
  barrier/atomic/futex behaviour (about 160,000 checks). `--rust-asan` also
  requires the archive's ASan imports to detect a deliberate one-past pointer
  passed to `swr_v1_locks_coroutine_try`. For a Rust-ASan archive on Linux:

  ```sh
  RUSTC_BOOTSTRAP=1 RUSTFLAGS='-Zsanitizer=address -Zexternal-clangrt=yes' \
    cargo rustc --locked --offline -p swoole-rs-locks --release \
    --target aarch64-unknown-linux-gnu --target-dir target/locks-rust-asan \
    --crate-type staticlib
  ```

- `upstream.py --source S --engine name=swoole.so ... [--php-extension E] [--case PATH] [--inventory-only]`
  (`locks-originals`): the 18 pinned `swoole_lock`, `swoole_atomic`,
  `swoole_coroutine_lock` and thread lock/atomic_ctor/barrier PHPTs through
  PHP's official runner. Load the same PHP extensions in both engines (on Linux
  `posix` is required). `--case` runs a subset, which leaves the gate failed.

## Other gates

- `core.py --source S --config CONFIG_H --archive A --build-root DIR --output R`:
  builds upstream and locks-only native trees (Linux) and runs the 14 unchanged
  lock GTests one process each.
- `state.py --engine ... [--require-zts]`: paired PHP witness (`state.php`) for
  integer wrap, CAS, lock behaviour and coroutine mutual exclusion; under ZTS
  also real threads sharing 32/64-bit atomics. Observations must match.
- `owned.py --engine ...`: NTS Atomic/Atomic\Long (1,792 checks each) and 128
  same-owner roundtrips per available lock kind.
- `threads.py --engine ... --php-extension sockets`: real ZTS threads with a
  barrier, 20,000 increments per Thread Atomic width and 2,000 mutex-protected
  updates. Requires ZTS engines; also used by `tests/modules/integration/zts.py`.
- `order.py --source S --engine ...`: instrumented admission/acquisition/receipt
  traces for the `coroutine_lock/lock.phpt` topology (`order.php`), modes
  `parallel` and `two-first`.
- `constructor.py --source S --archive A --output R [--sanitize] [--rust-asan]`:
  lock constructors with faults injected at the native pthread init/attribute/
  pshared boundaries; checks no leaked storage, attribute cleanup, exception
  code/message and first-error propagation through the direct ABI.
- `platforms.py --source S --output R`: compiles the header as C11/C++14 on the
  host and checks synthetic FreeBSD/Android (and Apple mobile on macOS) macros
  are rejected.
- `benchmark.py --prepare DIR --core-root CORE`, then `benchmark.py --prepared DIR`:
  mutex, rw-read, spin and atomic32 against both native libraries (Linux).
  Run timings with no other workload.
- `zts/Dockerfile` and `zts/build.py`: PHP 8.5 ZTS image and a build of
  reference and Rust thread-enabled extensions inside it (expects the repo at
  `/work`, the pinned upstream at `/reference` and a prior Linux
  `dev-rust-locks` build).

## Known failures

- `core.py` `rw_try_wr`: the upstream test relies on 1ms/2ms sleeps to make a
  try-lock contend with a held write lock, with no synchronisation. It fails
  intermittently in either engine (latest: reference failed, Rust passed).
  `gate.py` covers the same operations deterministically.
- `upstream.py` `tests/swoole_coroutine_lock/lock.phpt`: expects replies
  `value3, lock1, lock2` but nothing orders request arrival or lock
  acquisition (the coroutine lock is a CAS loop with backoff, not FIFO).
  Reference and Rust both produce `lock2, value3, lock1`, including on ZTS; the
  runner's retry WARN counts as a failure. `order.py` shows both engines
  produce that permutation with correct mutual exclusion.
- `upstream.py` on ZTS: `swoole_thread/lock.phpt` and `atomic_ctor.phpt`
  unlock a default pthread mutex from a non-owner thread, which POSIX does not
  guarantee. They are recorded `unsupported` without running, so the gate fails.
- `upstream.py` skips are not passes: macOS skips 4 and Linux NTS skips 3 of
  the 18, so the gate fails on those hosts.
- `constructor.py`: the native baseline leaks on failed construction and is
  reported as `native_baseline_passed: false`; the gate checks the Rust rows.
- `owned.py` on macOS: SPINLOCK is unavailable and not exercised.
