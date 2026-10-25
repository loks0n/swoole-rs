# HTTP/2 policy conversion

Rust (`crates/http2`) owns the settings/frame codecs, role-specific SETTINGS
decisions, body chunking, window actions, frame header and control payload
integers, the private client send queue container, and next-effect selection for
several client/server methods. Native code keeps the settings/window/stream
stores and all PHP, HPACK, socket, compression, coroutine and destructor effects.
Public headers are unchanged. The overlay keeps a native fallback behind
`SW_USE_RUST_HTTP2`.

## Running

From the repository root, run the core gate first. Every other gate reads its
report and reuses its overlay and archive:

```sh
python3 tests/modules/http2/gate.py --source /absolute/pinned/swoole \
  --output target/http2/core.json --sanitize [--archive libswoole_rs_ffi.a]
python3 tests/modules/http2/settings_calls.py --source /absolute/pinned/swoole \
  --core-report target/http2/core.json --output target/http2/settings.json
```

All `*_calls.py`, `response_*.py`, `request_headers.py` and `syntax_gate.py`
take the same `--source/--core-report/--output` arguments. Add
`--include /path/to/openssl/include` when the pinned headers need OpenSSL. Each
output's `-artifacts` directory must not exist yet. `tools/dev.py` registers all
of these as `http2-*` phases.

Native code is built with ASan and UBSan, excluding alignment because the pinned
inline codecs use unaligned integer casts. Rust archives are optimized and not
instrumented.

## Gates

Each gate extracts the actual pinned and patched function bodies, compiles both
against recording doubles for native effects, and compares effect order, emitted
bytes, return values and published state.

- `gate.py`: compiles the original and patched `src/protocol/http2.cc` (and the
  disabled overlay), runs Rust unit tests, and compares the core codec calls
  (`core_calls.cpp`) with a recording `Socket::send`.
- `settings_calls.py`: server SETTINGS loop and client lambda, with HPACK/trace
  doubles.
- `control_calls.py`: WINDOW_UPDATE/RST/GOAWAY bodies with allocation, send and
  reentry doubles; aligned native header encoding against Rust. PING payload
  bytes are uninitialized upstream and are not compared.
- `header_calls.py`: client header parser against scripted HPACK/Zend/zlib
  effects, with zlib on and off, plus role/media lookup against native locale
  predicates.
- `server_header_calls.py`: server header parser with HPACK, path, query, cookie,
  multipart and compression doubles, including reused inflater state and
  non-final input exhaustion.
- `queue_calls.py`: send and queue cleanup, `std::queue` against the Rust
  `VecDeque`, including short/negative IO, nested sends and draining error
  callbacks.
- `queue_failure_calls.py`: builds a `cfg(test)` Rust archive with an allocator
  that fails at chosen owner/growth calls, then runs the queue functions, the C++
  retry/handler wrapper and `Client::send`/cleanup. This is allocator-boundary
  coverage, not real system OOM.
- `window_calls.py`: server/client parser prefixes, WINDOW_UPDATE bodies and
  receive-flow fragments, with IO doubles that mutate window state.
- `receive_calls.py`: the server DATA case, including buffer-limit rejection,
  reset/removal, window publication and form/multipart selection.
- `response_headers.py`: server outgoing-header lambda and CRLF helper, both
  compression branches.
- `response_builders.py`: server header and trailer builders with the pinned
  `HeaderSet`, defaults/date/cookies, content length/encoding and HPACK reuse.
- `response_lifecycle.py`: response completion against the Rust next-effect
  controller (header retry, empty DATA, trailers, error close versus removal).
- `request_headers.py`: client request-header builder with the pinned
  `HeaderSet`, method/path defaults, authority ports and Host override.
- `publication_calls.py`: client response-publication suffix (properties,
  buffer clearing, return value, stream deletion).
- `write_calls.py`: client `write_data`, the DATA flag update and `send_request`.
- `send_calls.py`: server `send_header`/`send_body` and client `send_data`,
  including frame limits, chunk bytes and page-size splits.
- `connection_calls.py`: client `connect` and `close`.
- `decompression_calls.py`: client decompression with real zlib, both gzip
  levels, fragments and corrupt input.
- `file_calls.py`: file/range responses and the shared completion adapter.
- `syntax_gate.py`: syntax-checks all three production TUs with Rust on and off,
  using pinned headers exported into a private tree so untracked checkout
  config cannot leak in. `--configured-headers DIR` adds a configured SDK whose
  `identity.json` file hashes are checked before and after; `--php-config`
  selects the PHP headers.

## Original PHPTs

`full_originals.py --source DIR --output manifest.json` writes a
`corpus/upstream/run.py` manifest of the 70 pinned HTTP/2 PHPTs listed in
`inventory.json`, verifying each blob hash against the pinned source.
`tools/dev.py` runs it as `http2-full-originals`. Three of those PHPTs skip
unconditionally upstream; others need remote services, CLI tools or platform
features. Skips and unsupported cases are not passes.

## Not covered

Full PHP client/server runtime, real HPACK, callback/reentry/destructor
lifetimes, Zend bailout/longjmp, embedded versus external nghttp2, TLS/ALPN, h2c,
PHP thread modes and performance need separate gates.
