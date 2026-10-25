# Buffer and String gates

Gates for the Rust `swoole::Buffer` queue (`crates/buffer`) and `swoole::String`
storage (`crates/buffer/src/string`, gates in [string/](string/profiles.md)).
Native runners extract sources from pinned upstream
`8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e` into a disposable tree, apply the
patches from `migration/patches/buffer/manifest.json` (checksum and destinations
checked by `staging.py`) and link a supplied Rust archive. They never rebuild the
archive. `--sanitize` adds C++ ASan/UBSan; the Rust archive is not instrumented
unless built that way and declared with `--rust-asan` (see below).

## Native queue gates

| Command | Checks |
| --- | --- |
| `baseline.py --sanitize` | Pinned upstream only: original `core-tests/src/memory/buffer.cpp` assertions (64 seeded runs) plus a scatter/gather matrix that records upstream defects. |
| `hybrid.py --build-manifest M --sanitize` (or `--archive A`) | Same originals against the patched facade and Rust queue; the matrix must have zero byte/accounting mismatches. Also C ABI validation, native-token ownership, cached front identity, DATA callbacks on live bytes and quiescent fork. |
| `model.py --build-manifest M --sanitize` (or `--archive A`) | Six seeded 64-step sequences against an independent C++ reference queue, six facade sequences, and a fixture that replays each sequence once per allocation ordinal with that allocation failing. Failed operations must leave queue state unchanged. Details: [model.md](model.md). |
| `facade.py --source S --archive A --output R [--sanitize] [--rust-asan]` | Six seeded facade lifecycles (binary data, CLOSE tokens, partial offsets, mixed teardown); native and selected outcomes must match. |
| `iovec.py --source S --archive A --output R [--sanitize]` | Twelve positive POSIX iovec append cases; native and selected layout and observation counts must match. |
| `callbacks.py --source S --archive A --output R` | A throwing destroy callback must reach `std::terminate` (exit 77) for DATA pop, native-token pop and teardown in both engines. |
| `typed.py --source S --archive A --report R [--sanitize]` | Typed queue facade compiled and run under C++14/17/20. |
| `typed_layout.py --source S --report R` | `Buffer`/`BufferChunk` sizes and offsets under typed ON/omitted/zero; omitted and zero must preprocess to the same declaration as the control header. |

Run as `python3 tests/modules/buffer/<script>`; `S` is the pinned upstream
checkout (`target/upstream/src`).

## PHP gates

- `network.py --engine NAME=SO ... [--php PHP]`: ordered 4 MiB streaming, server
  reported queued bytes, sendfile offset/length, keep-alive and health after a
  cancelled response.
- `lifecycle.py --engine NAME=SO ... [--php-extension EXT]`: slow readers,
  stream/sendfile cancellation, half-close, churn and pending-write shutdown
  (corpus project `11-buffer-lifecycle`).
- `zend-oom.py --engine control=SO --engine candidate=SO --output R`: packs a
  4 MiB plain WebSocket frame, then repeats it under a memory limit so the real
  Zend String allocator fails. Exit code, stdout and stderr must match the first
  engine.
- Original PHPTs (`originals.json`, seven Swoole v6.2.2 tests plus
  `examples/test.jpg`):
  `python3 corpus/upstream/run.py --manifest tests/modules/buffer/originals.json --source S --engine upstream=SO --engine hybrid=SO --require-all --isolate-cases`.
  On Linux PHP 8.2 add `--php-extension curl --php-extension sockets` for both engines.

## Benchmark

Run only on an idle host. `benchmark.py --build-manifest M` compares optimized
upstream and Rust queue consumers (append/pop, contiguous and vectored, 50,000
cycles, five alternating repeats). To split preparation from timing:
`--prepare-dir D --output P.json` compiles and runs untimed checks, then
`--prepared-report P.json [--peek-front] --repeat 7 --iterations 10000 --output R`
times the prepared binaries after checking their hashes. `--previous-build-manifest`
adds a previous hybrid build to the comparison.

## Rust ASan

`hybrid.py`, `facade.py` and `string/gate.py` accept `--rust-asan` with
`--sanitize` for an archive built with Rust ASan. They refuse archives without
`__asan_report_` imports. Build such an archive on Linux with
`RUSTC_BOOTSTRAP=1 RUSTFLAGS='-Zsanitizer=address -Zexternal-clangrt=yes' cargo build --locked --offline -p swoole-rs-buffer --release --target=aarch64-unknown-linux-gnu`;
the explicit target keeps host build scripts uninstrumented. On macOS the
instrumented archive fails to link because Apple's runtime lacks
`___asan_version_mismatch_check_v8`. Precompiled Rust std stays uninstrumented.

## Known failures and intentional differences

- Upstream `Buffer::append(iovec)` defects, reproduced by `baseline.py`: chunk
  size 4 at offset 3 into a six-byte vector leaves length `4294967295` after pop
  (sixteen matrix cases have accounting mismatches); offset exactly at a vector
  boundary copies the wrong vector (four cases). Empty vectors and offsets at or
  beyond the total length are not executed against upstream because it can loop
  or read out of bounds. Rust rejects or handles these explicitly.
- Upstream frees DATA storage before its destroy callback; the Rust facade runs
  DATA callbacks on live bytes (`docs/buffer-abi-v1.md`).
- `swoole_server/sendfile_02.phpt` fails in both engines: `Swoole\Client::getSocket()`
  is missing because the build lacks `SWOOLE_SOCKETS_SUPPORT`.
- The lifecycle half-close case fails on upstream (truncated response) and on any
  hybrid built without the separate half-close fix.
- Optimized timing blocks default activation: String cold growth about 0.74x and
  write/reduce about 0.89x upstream (see [string/algorithms.md](string/algorithms.md)).

## Ownership

| Responsibility | Owner |
| --- | --- |
| Queue chunks, bytes, count, offset validation, failure rollback | Rust |
| Native sendfile/close tokens and callback invocation | C++, after Rust returns; DATA pop callbacks are noexcept |
| `BufferChunk` public view and mutable send offset | C++ caches the public view; callers keep its identity |
| POSIX iovec adaptation | C++ copies descriptors (8 on stack, heap fallback); Rust traverses and chunks |
| String growth, reservations, append/write/repeat/reduce/pop | Rust plans and applies edits; the standard libc allocator is called directly, custom/Zend allocation stays native |
| Binary search, delimiter scan, comparison, substring bounds | Rust (`memchr::memmem`); `split` returns to native before each handler call |
| Decimal integers | Rust `itoa` |
| Formatting/random output | Rust reservation/offset policy; printf varargs, entropy and base64 stay native |
| String move/clear/release and accessors | Native public metadata; no hidden Rust owner |

The ltrim/rtrim/strnpos/strnstr original String tests exercise native helpers in
`include/swoole_util.h` and `include/swoole.h`, not Rust code.
