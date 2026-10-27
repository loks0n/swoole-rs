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
| `server_gate.py` | coroutine handler routing, whole accept loop | |
| `payload_gate.py` | body/completion callbacks, option assignment, compression method selection | `--capabilities 0..7`, `--native-libc --locale NAME` |
| `response_gate.py` | known-header classifier (`build_header` is upstream's) | `--without-compression`, `--native-libc --locale NAME` |
| `codec_gate.py` | `HttpContext::compress` dispatch, levels, backend errors, partial writes | `--capabilities 1..7` |
| `settings_gate.py` | coroutine server startup settings body: alias order, null/false fallthrough, level clamp | `--without-compression` |
| `emission_gate.py` | `HttpContext::write`/`end` chunk/trailer packetization and split sends | `--without-compression`, `--without-zlib` |
| `file_gate.py` | `send_file` packetization and signed range validation | `--without-compression` |

`--capabilities` toggles the zlib/Brotli/Zstd branches in both original and
candidate. Capability 0 compiles the compression method out, so `codec_gate.py`
reports unsupported and exits 2; dev.py runs it for 1..7 only (#316).

Preserved native quirks (asserted by independent witnesses, not fixed): the
pointer-size token fast path, shrinking quote-trim bound, leading-hyphen key
formatting, case-sensitive substring and `q=0` encoding acceptance, uint32
length truncation, a successful `end` return after a failed trailer send, and
`parse_files=false` still publishing multipart files. `response_gate.py` keeps
modeled native chunked-length assertion failures as failures. The native
`LONG_MIN` helper overflow and signed-subtraction overflow in range validation
have no defined reference result and are excluded.

## Known gaps

- Mac's 501-position Request diagnostic has 67 original expectation failures in
  each engine (outcomes match across engines).
- Not covered: actual Zend GC/bailout/allocator faults, optional Brotli/Zstd
  execution, queue custody, cancellation, TLS, HTTP2, forced IO faults and
  complete response lifetime.
