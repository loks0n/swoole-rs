# M09 base64 conversion

ABI: [`docs/core-abi-v1.md`](../../../docs/core-abi-v1.md) and
`native/include/swoole_rs_base64.h`. Upstream pin:
`c7e514509451beafd4d70ce5b78943d51e76381c` (Swoole v6.2.4).

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

## Differential tests

```sh
cargo test -p swoole-rs-base64
```

`crates/base64/tests/upstream.rs` compares the Rust exports with the pinned
upstream C++, which `crates/oracle` compiles from unmodified copies under its
`upstream/` directory. Return counts and every output byte must match, with three
sentinels, 17-byte red zones and unaligned input: all one- and two-byte inputs,
all strings through length five over eleven byte classes, every byte in every
position through two quartets, and proptest cases for binary encode, base64-like
decode and truncated valid encodings. The two unmodified original core-test
assertions (`core-tests/src/protocol/base64.cpp`) run against the native adapter that
the base64 patch installs, with a deterministic random-byte fixture.

Rust's own bounds checks replace the previous ASan/UBSan build. The Rust codec has
no mutable state, so the earlier concurrency and fork runs are not carried over.

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
