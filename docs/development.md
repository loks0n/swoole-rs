# Development loops

`tools/dev.py` has three lanes, from fastest to complete:

```sh
# One crate or one named Rust test; no extension build.
python3 tools/dev.py edit --module buffer --test rollback

# Incremental build, ABI/native/PHP gates and the module's PHPT selection.
python3 tools/dev.py candidate --module websocket

# Reproduce one registered PHPT (candidate only).
python3 tools/dev.py candidate --module websocket \
  --case tests/swoole_websocket_server/pack.phpt \
  --hypothesis 'Header changes preserve the PHP frame representation' \
  --expect 'Original pack assertions pass'

# Immutable build, fmt/Clippy, module gates, all applications and all original
# PHPTs, with upstream as control.
python3 tools/dev.py integrate --module buffer --module websocket
python3 tools/dev.py integrate --all-modules   # every registered module; used by CI
```

- `--plan` prints the commands without running them.
- `--test` is edit-only; `--case` is candidate-only.
- Candidate runs only the hybrid; `--compare` also runs upstream. The WebSocket
  differential always runs upstream. Buffer changes select the full PHPT suite.
- `--benchmark` runs benchmarks after the correctness phases (and implies
  `--compare`); skipped if any phase failed. Stop other builds first.
- `--php-extension NAME` passes dynamic PHP modules through to runners.
- `--ccache PATH`, `--fix-halfclose`, `--match-child-php` and the optional
  switches from [hybrid build](hybrid-build.md) are forwarded to the builder or
  runners.
- `--gtest-prefix /abs/prefix` points native coroutine originals at a
  C++14-compatible GoogleTest (see below).

Edit and candidate stop at the first failure; integrate runs every phase and
fails if any failed. Each run writes logs, exit codes, phase durations,
hypothesis and expectation to `target/reports/dev/<UTC-time>-<id>/loop.json`.
For integration subsets, include the phases that produce reports consumed later
in the same run; the planner refuses missing prerequisites.

## Incremental builds

```sh
python3 tools/build_hybrid.py --dev --module buffer --module websocket
```

Dev builds live under `target/hybrid/dev/` with aliases like
`target/hybrid/dev-rust-buffer-websocket/` and never replace the immutable
aliases. `build-manifest.json` marks them `development`; `last-run.json` records
phase timings and whether make/relink/configure ran.

- Unchanged inputs skip make. A changed Rust archive forces a relink.
- Patched sources are staged from pinned Git objects; only changed files are
  copied, so unchanged mtimes survive.
- Changes to central `native/include/` headers, configure inputs, feature flags,
  toolchain or build-system patches select a new dev tree. Module-local headers
  are copied in and make rebuilds their consumers.
- Edits outside the declared overlays are rejected.
- One writer at a time: a concurrent builder fails instead of waiting.
- A dangling libtool `.lo` whose object was evicted is discarded and rebuilt.

Use immutable (non-`--dev`) builds for comparisons that must be reproduced.

`tools.build_hybrid.apply_patch_verified(tree, patch, targets, expected_sha256=None)`
applies a patch inside its own Git boundary, checks that every declared target
changed, and returns before/after hashes. An apply that leaves a target
unchanged is an error (Git can silently skip patches under an ignored parent
checkout).

## Caches

- Native test harnesses cache compiled binaries in `target/cache/native/`. The
  key covers compiler bytes, flags, compiler-discovered sources and headers,
  linked archives, host and environment; Rust fixtures also use rustc dep-info
  plus the toolchain's standard library archives. Binaries are checksum-verified
  and tests always re-execute. `--no-cache` or `SWOOLE_RS_NO_CACHE=1` disables it.
- ccache for the PHP extension build: see `tools/shared_cache.py`. It uses
  content compiler checks, no direct/depend mode, no hard links and empty
  sloppiness, and keeps exact source paths so `__FILE__` is unchanged. Per-build
  events go to the build log's `.ccache.log` sibling. `php_swoole.cc` always
  misses because it embeds `__DATE__`/`__TIME__`.
- Ad-hoc host commands: `python3 tools/shared_cache.py -- COMMAND`.

## PHPT runner

```sh
python3 corpus/upstream/run.py --engine upstream=target/upstream/src/modules/swoole.so \
  --jobs 4 --module channels --module table
```

`--jobs` batches only an audited list of process-local cases (including HTTP
request parser and WebSocket pack/unpack); timer, fork, listener and
shared-file cases always run in their own process group. `--isolate-cases` runs
one official runner per test. `--case` selects exact paths. Missing, duplicate
or foreign results fail; XFAIL and "passed on retry" warnings count as failures.
Results are saved atomically after each batch with `execution_status` of
`running`, `complete` or `interrupted`.

## Linux toolchain

```sh
python3 tools/linux_dev.py -- php --version
python3 tools/linux_dev.py -- python3 tools/build_upstream.py
python3 tools/linux_dev.py -- python3 tools/dev.py candidate --module buffer \
  --php-extension pdo --php-extension pdo_sqlite \
  --php-extension curl --php-extension sockets --php-extension tokenizer
```

The first call builds `tools/Dockerfile.dev` (Rust, PHP dev packages, CMake,
GoogleTest, nghttp2, libpq, curl, mbstring); `--rebuild-image` refreshes it.
The checkout is mounted read-only and synced into `target/linux-dev/`, which
keeps Linux objects, builds and Cargo downloads between runs. One writer at a
time; containers are removed after each run.

## Inspecting loops

```sh
python3 tools/dev_report.py                    # latest local loop
python3 tools/dev_report.py --lane integrate   # latest integration run
python3 tools/dev_report.py --linux            # latest Linux workspace loop
python3 tools/dev_report.py PATH/loop.json --limit 10 --json
python3 tools/dev_report.py AFTER/loop.json --compare BEFORE/loop.json
```

Read-only. Shows slowest phases, cache hit/miss reasons, failed-phase case
statuses or log tails (last 16 KiB), and per-engine counts. `/work` paths from
Linux runs map to the local workspace. JSON inputs over 32 MiB are reported as
unavailable. Exit status: 0 recorded pass, 1 recorded failure, 2 incomplete,
interrupted, malformed or contradictory (a "passed" loop with a failed phase).

`--compare` requires both loops to be terminal unless `--allow-partial` (which
exits 2). It groups phase exits into new failures, recoveries and unchanged
failures, and reports `new_failures` / `resolved_failures` per case only when
both sides have matching case inventories and an unchanged upstream control
binary. Other differences appear as `unqualified_status_changes`.

Tooling tests: `python3 -m unittest discover -s tests/dev -v`.

## Environment preflight

```sh
python3 tools/dev_environment.py \
  --source-root /abs/checkout --native-root /abs/native --output-root /abs/reports --json
```

Writes only to stdout. Reports Python version and SSL backend with TLS 1.2/1.3
context support (no sockets opened), versions of `--cc`, `--cxx`, `--rustc`,
`--cargo`, `--php`, `--php-config`, `--make`, `--openssl` (Cargo offline, rustup
auto-install off), and free space and mount type for each root. Blocks when a
filesystem has less than 4 GiB free, when PHP runtime and php-config versions
differ, or when a required TLS version is unavailable (`--require-tls 1.2`
narrows this). Exit 0 ready, 1 known blocker, 2 a probe unavailable. Probes time
out after 5 s (`--timeout`).

## Native core-tests

`tools/native_core.py` builds upstream's CMake/GoogleTest `core-tests` binary from
pinned Git blobs, optionally with module overlays and a given Rust archive, in a
private content-addressed tree.

```sh
python3 tools/native_core.py \
  --source target/upstream/src --config target/upstream/src/config.h \
  --module reactor --archive target/hybrid/builds/BUILD_ID/rust-prefix/lib/libswoole_rs_ffi.a \
  --exclude-unit core-tests/src/coroutine/iouring.cpp \
  --case 'reactor.*' --case stream.send --jobs 2 \
  --output target/reports/native-reactor.json
```

Omit `--module`/`--archive` for the upstream control. No tests run without
`--case` (exact names or globs). Each selected case needs exactly one matching
XML result. Excluded units are reported unsupported and keep the overall exit
status 1.

- On Linux the reference fails to compile `core-tests/src/coroutine/iouring.cpp`
  (tests use optional declarations without guards), so `--exclude-unit` it.
  macOS has further Linux-only compile assumptions.
- The binary is copied to `src/bin/core-tests` before running: pinned `main.cpp`
  finds fixtures relative to `argv[0]/../`.
- macOS needs CMake, nghttp2, libpq, OpenSSL and a C++14-compatible GoogleTest.
  Homebrew GoogleTest 1.18 rejects C++14; build 1.12.1 into a prefix and put it
  first in `CMAKE_PREFIX_PATH` and `PKG_CONFIG_PATH`, followed by the OpenSSL and
  libpq pkgconfig directories. Pass `--php-dir /opt/homebrew --openssl-dir
  /opt/homebrew/opt/openssl@3`, and add nghttp2's `pkg-config --libs-only-L` output to
  `LDFLAGS` (pinned CMake links nghttp2 by bare name).
- `--ccache PATH` uses a private 1 GiB cache with `-fdebug-prefix-map`, so
  relocated trees reuse compiler output.

`tools/extension_identity.py` records the identity of an extension binary that
has no build manifest.
