# Coroutine validation

Reference pin: `8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e`. `PINNED_TREE` below is
the pinned upstream Git checkout (`target/upstream/src`); `ARCHIVE` is the real
Rust FFI static archive. Most gates refuse an existing `--report` path.

## Original tests

```
python3 tests/modules/coroutine/upstream.py --source PINNED_TREE --engine NAME=SO [--group G] [--case tests/...] --output OUT.json
python3 tests/modules/coroutine/core.py --source PINNED_TREE --config CONFIG_H --archive ARCHIVE \
  --build-root PRIVATE_DIR [--sanitize] [--ucontext] [--rust-asan] [--lifetime-only] --output OUT.json
```

`upstream.py` runs all 201 pinned PHPT originals (130 coroutine, 44 channel, 27
scheduler) with PHP's official runner and the shared support adapter. `--group`
or `--case` selects a subset; the gate only passes when no case is left
unmeasured. `tests/swoole_coroutine/cancel/socket.phpt` needs a free UDP 9601.
Route/DNS-dependent cases need `--external-network`.

`core.py` builds full native reference and coroutine-only libraries and runs the
32 unchanged GoogleTests, plus three supplemental real-context tests from
`lifetime.cpp`, each in its own process group. `--ucontext` derives a private
config selecting ucontext. `--rust-asan` requires ASan imports in the archive;
ASan stack-switch warnings yield `warned`, not `passed`. On macOS pass
`--gtest-prefix` pointing at a C++14-compatible GoogleTest (1.12).

## Source-body and ABI gates

```
python3 tests/modules/coroutine/compile_gate.py --source PINNED_TREE [--registry] [--timing] [--stack-usage] \
  [--backend asm|ucontext|thread] [--standard c++14|c++17] --report OUT.json
python3 tests/modules/coroutine/ordered_gate.py --source PINNED_TREE --archive ARCHIVE --sanitize --report OUT.json
python3 tests/modules/coroutine/channel_state_gate.py --source PINNED_TREE [--archive ARCHIVE] --report OUT.json
python3 tests/modules/coroutine/channel_state_sdk.py --source PINNED_TREE --sdk-export SELECTED/export.json \
  --native-export NATIVE/export.json [--backend B] [--registry-v2] --report OUT.json
python3 tests/modules/coroutine/{tokens,stack,timing,scheduler,registry}.py --source PINNED_TREE --archive ARCHIVE --sanitize --report OUT.json
python3 tests/modules/coroutine/{creation,entry,print}.py --source PINNED_TREE --archive ARCHIVE --report OUT.json
python3 tests/modules/coroutine/production_stack.py --source PINNED_TREE --source-ref REF \
  --selected-export SELECTED/export.json --native-export NATIVE/export.json --output OUT.json
python3 tests/modules/coroutine/thread_context_audit.py --source PINNED_TREE --output OUT.json
```

- `compile_gate.py` compiles original, patched and disabled `base`, `channel`,
  `context` and `thread_context` translation units; the disabled overlay must
  fail closed with its guard message.
- `ordered_gate.py` compiles pinned and selected scheduler/channel bodies around
  deterministic callback, clock, timer and registry facades: nested finish,
  bailout suppression, yield/cancel/timeout, timer allocation failure, throwing
  callbacks, close wake order, fairness and stale errors.
- `channel_state_gate.py` runs the Rust unit tests (ordinary and with Rust ASan),
  stages the current overlays, runs `tokens.py`, `creation.py`,
  `entry.py` and `print.py`, and runs the C11/C++ ABI fixtures (`tokens.c`,
  `channel_state.c`, `status.c`, `context_cells.c`, `identity.c`, `creation.c`,
  `entry.c`, `print.c`, `registry_policy.c`, `swap.c`, `bailout.c`).
- `channel_state_sdk.py` compiles five complete core/PHP translation units in
  native, disabled, M06-only and combined SDK profiles under C++14/17 (30 rows),
  checks Rust imports in each object, and compares Channel/Coroutine/Context
  layouts. The disabled preprocessed classes must equal native.
- `tokens.py` (Channel queue storage), `stack.py` (stack markers), `timing.py`,
  `scheduler.py` (`--registry` adds the Rust registry) and `registry.py`
  (get/count/GDB) compare native vs selected source fragments on inert metadata.
  `--rust-instrumented` (Linux with `--sanitize` only) also requires Rust ASan
  imports in the archive.
- `creation.py`, `entry.py`, `print.py` compare complete pinned vs selected
  registration, entry-wrapper and `print_list` bodies with inert effects.
- `production_stack.py` builds the Context constructor/destructor/query into a
  private PHP addon against each engine's SDK and checks marker observations.
- `thread_context_audit.py` runs the pinned thread-context baton bodies with an
  error-checking mutex; it exits non-zero if the diagnostic fails.

## Registry order

```
python3 tests/modules/coroutine/registry_order.py [--archive ARCHIVE] [--native-sanitize | --sanitize] --report OUT.json
python3 tests/modules/coroutine/registry_rust_checks.py [--sanitize] --report OUT.json
python3 tests/modules/coroutine/registry_sdk.py --source PINNED_TREE --sdk-export SELECTED/export.json --report OUT.json
python3 tests/modules/coroutine/registry_gnu_source.py --candidate-dir CAPTURE --report OUT.json
python3 tests/modules/coroutine/registry_gnu_body.py --oracle-dir ORACLE --candidate-dir CAPTURE [--native-sanitize] --report OUT.json
python3 -m unittest registry_gnu_source_test   # from tests/modules/coroutine
```

The selected registry keeps stable Rust entries in a live linked sequence with
subordinate bucket heads, reproducing the iteration order of LLVM libc++ 210106
ABI1 `std::unordered_map<long,T*>`: load factor 1, 1 grows to 2, powers of two
stay powers, other sizes use the next prime; insertion prepends within a bucket;
erase keeps the bucket count; replacement keeps position; clear keeps buckets.
An `operator[]` miss publishes null before assignment.

- `registry_order.py` checks long-key boundaries, null misses, replacement,
  clear/reinsert, collisions, growth and erase against the local standard
  library after every operation (C++14/17, O0/O2). With `--archive` it links a
  supplied FFI archive, which must report ABI 1 and coroutine bit 15.
- `registry_rust_checks.py` runs the registry Rust unit tests, plus clippy and
  rustfmt; `--sanitize` builds with Rust ASan and requires report imports.
- `registry_sdk.py` compiles complete `src/coroutine/base.cc` and
  `ext-src/swoole_coroutine.cc` with REGISTRY_V2 OFF/ON under C++14/17 (eight
  profiles) against a frozen SDK, and checks registry imports. Use
  `--private-sdk-report` to reuse an earlier private SDK copy, and
  `--producer-path-prefix`/`--mounted-root` for a read-only container mapping.
- GNU (Linux) candidate: `registry_gnu_source.py` verifies captured libstdc++ 12
  headers and GCC 12.2.0 sources against their package manifests and checks the
  Rust prime table against the source. `registry_gnu_body.py` compares the GNU
  Rust policy against eight captured GNU bodies. Both need a captured candidate
  directory; neither covers installed Linux behaviour.

## Benchmarks

```
python3 tests/modules/coroutine/prepare_benchmark.py --core-build CORE_PAIR_DIR --output NEW_DIR
python3 tests/modules/coroutine/benchmark.py --prepared NEW_DIR --exclusive-host-lease ID --output OUT.json
python3 tests/modules/coroutine/registry_prepare_benchmark.py --export SELECTED_EXPORT --source PINNED_TREE --report OUT.json
```

`prepare_benchmark.py` copies an optimized, assertion-enabled native core pair
(`core-upstream`, `core-rust`), links `benchmark.cc` and runs untimed
ten-operation checks for create/yield/channel/cancel/fanin. `benchmark.py`
verifies the prepared binary/library hashes and runs alternating timed trials.

`registry_prepare_benchmark.py` requires an optimized non-debug Rust profile,
rebuilds the M06 overlays, and compiles native and selected
`registry_benchmark.cc` harnesses (C++14 `-O2 -Werror`). Six workloads over 512
entries (clear/reinsert, replacement, get/count hits and misses,
erase/reinsert, live traversal, GDB iterator) must match between engines.
Artifacts are made read-only and listed in `artifacts_sha256`. Timing is run
separately with `BINARY --measure WORKLOAD LEASE_ID`, which times 4096
iterations with `steady_clock`. Run benchmarks only on an otherwise idle host.

## Known failures and blocked activation

- `core.py --ucontext` on macOS fails all 32 originals per engine, including a
  native SIGSEGV in `_setcontext`. Assembly contexts pass on macOS and Linux.
- `ordered_gate.cc` and `production_stack.cc` still model the old protected
  Channel/Context fields and direct imports, so they do not match the current
  overlays.
- `registry_order.py --sanitize` (mixed Rust/C++ ASan) fails to link on Apple
  clang: the Rust object imports an ASan version-check symbol the clang runtime
  lacks. `--native-sanitize` and `registry_rust_checks.py --sanitize` pass.
- `channel_state_sdk.py --backend ucontext` fails on the native unused-`sp`
  `-Werror` warning.
- REGISTRY_V2 is qualified only for Apple libc++ 210106 ABI1 with 64-bit
  `long`/`size_t`; the selected header refuses other platforms, including
  Linux. It stays OFF by default.
- Optional thread-context is unsupported; `core.py` rejects a config defining
  `SW_USE_THREAD_CONTEXT`, and `thread_context_audit.py` reports the expected
  ownership violations.
- Not covered: real Coroutine creation/switching through Rust paths, callbacks,
  lifetime and allocation failure, ZTS, Linux runtime, and performance.

The C ABI contract is [native/coroutine/contract.md](../../../native/coroutine/contract.md).
