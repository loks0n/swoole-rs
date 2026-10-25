# Rust timer ASan

Instruments the Rust timer queue as well as the native C/C++ callers. Test-only;
no production flags or ABI change. Linux, with the pinned reference available:

```sh
RUSTC_BOOTSTRAP=1 RUSTFLAGS='-Zsanitizer=address -Zexternal-clangrt=yes' \
  cargo rustc -p swoole-rs-timer --release --offline --locked \
  --target-dir target/rust-asan-timer --crate-type staticlib -v
python3 tests/modules/timer/kernel.py --no-build --sanitize --rust-asan \
  --archive target/rust-asan-timer/release/libswoole_rs_timer.a \
  --output target/reports/timer-rust-asan-kernel.json
python3 tests/modules/timer/core.py --source target/upstream/src \
  --config target/core-config.h --build-root target/core-rust-asan \
  --archive target/rust-asan-timer/release/libswoole_rs_timer.a \
  --sanitize --rust-asan --output target/reports/timer-rust-asan-core.json
```

`--rust-asan` declares an externally instrumented archive; it does not build
one. Both gates reject an archive without ASan report imports, and `kernel.py`
requires `--no-build` so it cannot replace the supplied archive.

On Linux the C ABI gate passes all 13 topics and the original GoogleTest gate
passes 9/9 upstream and 9/9 Rust with native ASan/UBSan, leak detection and the
Rust archive instrumented. The precompiled Rust standard library is not
instrumented. Exhaustion/OOM injection and concurrent-fork allocator safety are
outside this gate.

Rust unit tests under ASan (including the allocation-failure tests) pass on
Linux and macOS:

```sh
RUSTC_BOOTSTRAP=1 RUSTFLAGS=-Zsanitizer=address cargo test -p swoole-rs-timer \
  --release --offline --locked --target-dir target/rust-unit-asan -v -- --nocapture
```

macOS leak detection is off because its runtime lacks it.

## Known failures

- macOS: native linking of an instrumented caller with the Rust ASan archive
  fails. Apple's runtime lacks `___asan_version_mismatch_check_v8`; selecting
  Rust's bundled runtime instead fails because Apple Clang's caller imports
  `___asan_version_mismatch_check_apple_clang_2100`. A matching
  compiler/runtime pair is required.
- PHP-loaded Linux ASan is blocked by PHP's `RTLD_DEEPBIND` loading (see
  [hybrid.md](hybrid.md)).
