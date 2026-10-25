# PHP HTTP binding correctness

The ABI contract is in [docs/http-bindings-abi-v1.md](../../../docs/http-bindings-abi-v1.md).

## Native differential gates

Each `*_gate.py` extracts the actual pinned and patched function bodies from
`ext-src/swoole_http_*.cc`, compiles both against shared native effect facades
(`*_oracle.h`) and the Rust archive, and compares outputs, effect order, partial
state and fault exits. Native code always runs under ASan/UBSan.

```sh
rustc --edition 2024 --crate-type staticlib -C opt-level=2 \
  crates/httpbindings/src/lib.rs -o /private/target/libhttpbindings.a
python3 tests/modules/httpbindings/cookie_gate.py --source /readonly/pinned/git \
  --archive /private/target/libhttpbindings.a --output /private/target/cookie.json
```

All gates take `--source`, `--output` and either `--archive PATH` or
`--rust-sanitize` (Linux: build an ASan Rust archive privately; std stays
uninstrumented).

| Gate | Checks | Extra flags |
|---|---|---|
| `cookie_gate.py` | `HttpCookie::toString` field/flag/expiry/binary states, effect faults, warning reentry | |
| `request_gate.py` | header/URL callbacks, token list, quote trim, response key formatting | `--without-compression` |
| `server_gate.py` | receive body, coroutine handler routing, whole accept loop | |
| `payload_gate.py` | body/completion callbacks, option assignment, compression method selection | `--capabilities 0..7`, `--native-libc --locale NAME` |
| `response_gate.py` | known-header classifier and `build_header` tail | `--without-compression`, `--native-libc --locale NAME` |
| `codec_gate.py` | `HttpContext::compress` dispatch, levels, backend errors, partial writes | `--capabilities 0..7` |
| `settings_gate.py` | coroutine server startup settings body: alias order, null/false fallthrough, level clamp | `--without-compression` |
| `emission_gate.py` | `HttpContext::write`/`end` chunk/trailer packetization and split sends | `--without-compression`, `--without-zlib` |
| `file_gate.py` | `send_file` packetization and signed range validation | `--without-compression` |

`--capabilities` toggles the zlib/Brotli/Zstd branches in both original and
candidate. Capability 0 compiles the compression method out: `codec_gate.py`
reports unsupported, `passed=false` and exits 2.

Preserved native quirks (asserted by independent witnesses, not fixed): the
pointer-size token fast path, shrinking quote-trim bound, leading-hyphen key
formatting, case-sensitive substring and `q=0` encoding acceptance, uint32
length truncation, a successful `end` return after a failed trailer send, and
`parse_files=false` still publishing multipart files. `response_gate.py` keeps
modeled native chunked-length assertion failures as failures. The native
`LONG_MIN` helper overflow and signed-subtraction overflow in range validation
have no defined reference result and are excluded.

## Real PHP gate

`php_gate.py` checks an actual loaded candidate extension against a native
control build, then runs the PHP suites (`cookie_php.py`, `server_php.py`,
`request_php.py`, `compression_php.py`, `settings_php.py`, `emission_php.py`,
`settings_fatal.py`, `file_php.py`):

```sh
python3 tests/modules/httpbindings/php_gate.py \
  --engine upstream=/readonly/reference.so --engine candidate=/readonly/swoole.so \
  --source-ref FULL_COMMIT_SHA \
  --build-manifest candidate=/readonly/build-manifest.json \
  --archive candidate=/readonly/libswoole_rs_ffi.a --output /private/php.json
```

Before running the suites it verifies that the build manifest matches the loaded
extension, feature bit 2097152, the linked archive, the five caller patches and
headers, and that every module Rust source and shared Cargo/FFI entrypoint
matches `--source-ref`. Older manifests without `inputs.rust_sources_sha256`
also need `--source-receipt candidate=/readonly/receipt.json` (fields
`source_commit`, `source_inputs`, `inputs_unchanged`, `returncode`).

Each suite also runs standalone with `--engine NAME=PATH ... --output PATH`.
`settings_fatal.py` expects native exit 255 with exact warning/error output for
wrong-type, directory and Stringable-throw startup cases; these are compared for
parity, not counted as passes.

## Known gaps

- Mac's 501-position Request diagnostic has 67 original expectation failures in
  each engine (outcomes match across engines).
- Not covered: actual Zend GC/bailout/allocator faults, optional Brotli/Zstd
  execution, queue custody, cancellation, TLS, HTTP2, forced IO faults and
  complete response lifetime.
