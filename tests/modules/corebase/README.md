# Core-base validation

The corebase overlay patches `src/core/base.cc` so that helper policy (type
size, gcd/lcm, stoi env parsing, itoa/radix/hex, version compare, dirname,
recursive mkdir), lifecycle sequencing (init, clean, thread init/clean, fork,
task tmpdir) and hook insertion decisions come from Rust. Native code keeps all
globals/TLS, allocation, syscalls, logging and callback execution. See
`native/corebase/contract.md`.

On Homebrew macOS add `--include /opt/homebrew/opt/openssl@3/include` to the
native-TU gates.

## Registered gates

- `differential.py --source CONFIGURED_PINNED --output R [--archive A] [--sanitize] [--signed-char | --unsigned-char] [--include DIR]`
  (`corebase-native`): compiles the complete original and patched `base.cc`
  into separate binaries with `driver.cc`, feeds both the corpus from
  `cases.py` and requires identical output/errno, plus 934 independently
  expected values. It also runs eight extracted upstream `TEST(base, ...)`
  bodies (dec2hex, hex2dec, version_compare, common_divisor, common_multiple,
  dirname, itoa, type_size) and the `allocator.cc` strndup interposer. Without
  `--archive` it builds the crate offline with `itoa=1.0.18`. The patched
  binary must contain real calls to each Rust helper; the original none.
  `--unsigned-char` also covers bytes 128..255.
- `mkdir.py --source S --archive A --output R [--sanitize]` (`corebase-mkdir`):
  270 traced `swoole_mkdir_recursive` cases (30 paths x 9 syscall scenarios,
  through `mkdir-shim.h`/`mkdir-driver.h`) compared between original and
  patched, plus real private-filesystem checks per engine.
- `php.py --source S --engine native=... --engine rust=... --output R [--fork | --task-directory [--task-directory-fixture-only]]`
  (`corebase-php`): needs one engine with and one without feature bit 8192.
  Default: `consumers.php` (package-length formats, Content-Length, chunk
  lengths) and three upstream PHPTs. `--fork`: `fork-consumers.php`,
  `fork-logger.php`, coroutine/async fork guards and seven Process PHPTs.
  `--task-directory`: `task-directory.php` (settings, startup creation,
  file-backed pack/unpack, error path) and `task/unpack.phpt`; requires the
  extension to define and call `swr_v1_corebase_task_tmp_next` unless
  `--task-directory-fixture-only`. On Linux add `--php-extension sockets`
  (and `curl` if built with curl hooks).
- `mkdir_startup.py --engine native=... --engine rust=... --output R`
  (`corebase-startup`): PHP startup through `sys_temp_dir` (create, repeated
  slashes, file parent), comparing warnings and `swoole_last_error`. The Rust
  build manifest must contain the current corebase patch.
- `canonical.py --source PINNED_GIT --config CONFIG_H --archive A --output R [--jobs N] [--openssl-dir P] [--php-dir P] [--ccache EXE | --no-ccache]`
  (`corebase-lifecycle`): builds a native and a corebase-only full library
  with `tools/native_core.py`, requires the selected upstream base GTests to
  pass in both (12 on macOS, all 33 active on Linux), then runs
  `prepare_benchmark.py` and `lifecycle_gate.py` on that pair. Its report is
  also consumed by `tests/modules/tls/gate.py --allocation-native-report`.

## Lifecycle pieces

- `prepare_benchmark.py --source NATIVE_TREE --native-build R --rust-build R --identity ID --output R`:
  compiles `benchmark.cc` against both libraries, verifies the loaded library,
  and checks all 11 workload checksums with no timing.
- `lifecycle_gate.py --prepared R --archive A --output R`: checks the prepared
  pair was built from the current overlay and archive, then runs
  `hook_lifetime.py` for cleanup/thread, fork, task-directory and
  task-lifetime drivers (plus fork-failure, init and init-host on Linux).
- `hook_lifetime.py --prepared R --output R --driver hooks|fork|fork-failure|init|init-host|task-directory|task-lifetime [--require-fork] [--require-init] [--require-task-tmp] [--require-lifecycle]`:
  compiles the matching `*.cc` witness against both libraries and compares its
  trace to the expected one (for `init`, native and Rust traces must match).
  The `--require-*` flags use `lifecycle_proof.py` to require actual call paths
  from the native facades to the Rust entry points. `fork-failure`, `init` and
  `init-host` interpose syscalls and are Linux-only.
- `benchmark.py --measure --prepared R --output R [--counts PROFILE] [--repetitions N]`:
  times the prepared workloads (seven alternating repetitions by default) and
  fails if any Rust median is slower. Run with no other workload on the host.
  It has not been run yet.
- Pure Rust policy checks:
  `rustc --edition=2024 --test tests/modules/corebase/hook-policy.rs -o target/corebase-hook-policy && target/corebase-hook-policy`
  (likewise `init-policy.rs`, `task-directory-policy.rs`).

`patching.py`, `cases.py`, `lifecycle_proof.py` and `supervisor.py` are shared
helpers. `supervisor.py` runs child Python tools in-process so SIGTERM/SIGINT
unwind their process groups; a forced SIGKILL does not.

## Known failures and gaps

- The full native GTest inventory fails in both engines: `canonical.py`
  excludes units that do not build or run on the host (on macOS coroutine/hook,
  coroutine/system, lock/lock, network/socket, os/os, os/process_pool,
  os/signal, server/http_server, server/server, coroutine/iouring; on Linux
  coroutine/iouring), so `full_native_inventory_passed` is false. Only the
  selected base cases gate the lifecycle comparison.
- macOS `base.futex` fails its wakeup assertion and times out in both engines
  (the native fallback returns 0 where the test expects 1). Five macOS base
  cases that use fixed `/tmp` paths are not run.
- On Linux, an inherited `LD_DEBUG` breaks `base.shell_exec`'s exact stderr
  check; the gates strip loader tracing variables.
- Locales missing on the host are reported as unavailable, not passed.
- The corpus targets LP64 macOS/Linux only.
- Not covered: Rust-side sanitizers, malloc/system OOM, PHP init with the Rust
  init path, `SW_THREAD` runtime, and performance.
