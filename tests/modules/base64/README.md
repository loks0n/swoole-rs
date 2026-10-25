# M09 base64 conversion

ABI: [`docs/core-abi-v1.md`](../../../docs/core-abi-v1.md) and
`native/include/swoole_rs_base64.h`. Upstream pin:
`8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e` (Swoole v6.2.2).

`crates/base64` replaces both low-level algorithms with allocation-free Rust.
The optional overlay removes the old algorithms and mutable alphabet tables from
`src/core/base64.cc`; its native adapter only forwards existing C++ symbols to
the Rust exports.

The decoder intentionally accepts incomplete quartets, stops at the first `=`,
and preserves provisional writes before invalid data returns zero. It does not
skip whitespace. Normal completion writes a terminating NUL. Untouched bytes stay
untouched, including on failure. Rust uses `MaybeUninit<u8>` output storage, so C
callers may pass uninitialized writable storage. Only the FFI boundary constructs
slices; checked size/address arithmetic rejects null and unrepresentable ranges.
Allocation validity and disjointness remain caller preconditions.

The pinned encoder has undefined behavior for zero input: its unsigned index
underflows and may read before the input. **Zero-length encode is excluded from
the C++ oracle.** The Rust definition writes a NUL and returns zero; null input
is permitted for zero length.

The encoder processes full three-byte groups without padding decisions; one tail
step supplies padding. The decoder classifies each byte with an immutable
256-byte table generated from the canonical alphabet.

## Caller audit

Production low-level encoder calls in the pinned source:

| Caller | Input and output ownership |
| --- | --- |
| `src/protocol/http.cc`, `HttpProxy::get_auth_str` | Native stack buffers, formatted `username:password` |
| `src/core/string.cc`, `String::append_random_bytes` | Native random input and separately allocated encoded output; zero requested length is not guarded here |
| `ext-src/swoole_http_client_coro.cc`, `Client::set_basic_auth` | Native `std::string` `username:password`, separate Zend allocation |
| `ext-src/swoole_websocket_server.cc` | 20-byte SHA1 digest, separate native handshake output |

No production code calls the low-level `swoole::base64_decode`; only its original
core test does. The `swoole_stdext.cc` aliases, the embedded PHP library and the
client handshake's `php_base64_encode` use PHP's own base64, not this code.

## Differential check (`check.py`)

```sh
mkdir -p target/reports/base64
rustc --edition 2024 --test crates/base64/src/lib.rs -o target/base64-tests
./target/base64-tests
python3 tests/modules/base64/check.py --source /path/to/pinned/upstream --output target/reports/base64/differential.json
python3 tests/modules/base64/check.py --source /path/to/pinned/upstream --sanitize --output target/reports/base64/differential-asan.json
```

Options:

- `--archive PATH` links a published hybrid `libswoole_rs_ffi.a` instead of
  compiling the crate privately (`tools/core_check.py` does this from a build
  manifest).
- `--sanitize` builds the C++ oracle, adapter and harness with ASan/UBSan;
  adding `--rust-sanitize` also instruments the private Rust build (Rust's
  precompiled std stays uninstrumented). Passed on Linux with GCC's ASan runtime;
  untested on macOS.
- `--encode-positive-only` / `--decode-positive-only` run only defined,
  sequential encode or canonical decode cases (no malformed, fault, thread, fork
  or benchmark execution) and report `full_gate_passed: false`.
- `--prepare-positive-benchmark` (with a positive profile, unsanitized) runs the
  untimed check-only preflight of the 14 canonical workloads and keeps the
  executable with `.a` and `.sources.tar.gz` siblings.

The runner reads original source, header and core test from pinned Git objects,
applies the checksum-declared overlay in scratch, and requires the result to equal
`native/base64/base64.cc` byte for byte. It builds the original C++ into a
separate `oracle` namespace and links the patched adapter with an optimized Rust
static library, then checks both Rust symbols in the final executable. Negative
compile gates prove the overlay rejects builds without `SWOOLE_RS_BASE64`, both
by explicit define and by a `config.h` that omits the feature.

The two unmodified original core-test assertions run against the Rust adapter
with a deterministic replacement for the random-byte fixture. Differential
checks compare return counts and every output byte with three sentinels, 17-byte
red zones and unaligned buffers: all one- and two-byte inputs, all strings
through length five over eleven symbols, every byte in every position through
eight-character groups, and 4,096 larger binary/valid/incomplete cases. It also
runs 1,600 concurrent encode/decode calls and a fork child.

## Benchmarks

The validated executable is kept beside the report as `<report>.bin`. Run it with
`--check-benchmark` for the untimed preflight (19 workloads, comparing outputs)
or `--benchmark` to measure seven alternating-order trials of upstream/Rust
encode/decode at 1, 2, 3, 20, 64, 1,024 and 65,536 bytes plus invalid and
incomplete decode workloads. Positive-only executables use
`--positive-benchmark` / `--encode-positive-benchmark`. Never benchmark the
sanitizer build, and run measurements without concurrent workloads.

`test_positive_preparation.py` compiles the benchmark workload selection with
inert codecs and checks it never reads the clock in check-only mode:

```sh
python3 -m unittest tests/modules/base64/test_positive_preparation.py
```

## PHP consumers

`consumers.py --extension EXTENSION --manifest BUILD_MANIFEST --output REPORT`
(registered in `tools/dev.py` as `base64-consumers-*`) checks the real coroutine
HTTP client's `setBasicAuth` output against Python Base64 for 13 credential
pairs (empty, binary/NUL, padding boundaries, up to 8 KiB), 12 HttpProxy
authorization cases, and 32 WebSocket server handshake responses against Python
SHA1/Base64, all on loopback ephemeral ports. The extension's SHA-256 must match
the manifest. Linux builds with native curl hooks need `--php-extension curl`.
The proxy path keeps its native `%.*s` embedded-NUL truncation and 255-byte
bound; the checks expect that behavior.

`original.py --source PINNED_SOURCE --engine NAME=EXTENSION --output REPORT`
runs the unchanged original `set_basic_auth.phpt` with PHP's official runner
against a loopback HTTPBin-compatible fixture selected through the test's own
`HTTPBIN_SERVER_HOST/PORT` variables.

## Other probes

- `x86_probe.rs` includes the production source unchanged in a freestanding
  `no_std` x86_64 Linux ELF and exits nonzero on any failed check. Build with
  `--target x86_64-unknown-linux-gnu`, panic abort, static relocation and link
  args `-nostdlib -static -no-pie`, then run through
  `tools/linux_dev.py -- /repo/target/NAME` (Linux binfmt).
- `combined_canonical.c` runs 2,224 sequential canonical cases through the C11
  headers against a Cargo release archive built with only `base64,crc32`.

## Open gates

Linux runs of the positive-only and preparation profiles, native x86 C++/PHP
integration, MemorySanitizer/Miri, matched optimized performance and default
activation remain open.
