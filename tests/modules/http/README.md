# HTTP checks

The HTTP module moves first-party helpers, request/header/chunk framing, cookies,
proxy policy, static paths/ranges/headers/calendar/rewrite/index rendering and
multipart accounting into Rust behind `SWOOLE_RS_HTTP`. Native code keeps PHP and
server configuration, allocation/IO/logging, libc calendar/locale behaviour,
`std::regex` and the external llhttp/multipart parsers. See
[the ABI contract](../../../native/http/contract.md) for exact contracts.

Rust unit tests and the archive the native gates link against:

```sh
cargo test --locked -p swoole-rs-http
cargo clippy --locked -p swoole-rs-http --all-targets -- -D warnings
cargo build --locked -p swoole-rs-ffi --no-default-features --features http --release
```

## Native differential gates

Each gate extracts the pinned (v6.2.4, `c7e514509451`) and patched native method
bodies into separate namespaces, applies the owned overlay through
`apply_patch_verified` in a temporary tree, compiles the whole selected native
translation unit as C++14, and compares outcomes, effect traces, errno and
partial publication through deterministic native facades. Native code runs under
ASan/UBSan; the Rust archive is uninstrumented unless `--rust-sanitize` is used
(Linux; builds a private ASan HTTP archive, precompiled std stays
uninstrumented). Gates marked `[A|R]` take `--archive PATH` or `--rust-sanitize`;
the rest require `--archive PATH`. All take `--source PINNED_GIT --output REPORT`.
`tools/dev.py` registers most of them.

| Script | Checks |
| --- | --- |
| `gate.py` (`--url-positive-only`) | URL encode/decode, boundary, method, status helpers; five unchanged original core-test bodies |
| `framing_gate.py` | Request framing and buffer metadata; original `get_protocol`, `has_expect_header`, `all_method` bodies |
| `range_gate.py` [A\|R] | `parse_range`, including allocation-failure injection and the pinned `sw_snprintf` |
| `headers_gate.py` | FormData/header callbacks, errno, reentrancy |
| `proxy_gate.py` [A\|R] (`--auth-positive-only`) | Proxy auth packing/handshake with actual base64 |
| `static_gate.py` [A\|R] (`--positive-only`) | Static response method, send order, HEAD/keep-alive changes |
| `path_gate.py` [A\|R] | `try_serve`/`get_absolute_path`/`set_filename` |
| `conditional_gate.py` | Date callers with libc `strptime`/`gmtime`/`mktime` |
| `index_page_gate.py` (`--positive-only`) | `make_index_page` with pinned String `format_impl` |
| `multipart_gate.py` | Multipart upload accounting callbacks |
| `multipart_headers_gate.py` [A\|R] (`--positive-only`) | Multipart header field/value and filename callbacks |
| `multipart_parser_gate.py` [A\|R] | Pinned C multipart parser plus all seven callbacks with real temp files |
| `multipart_emit_gate.py` [A\|R] | Header-complete/data-end/part-begin/body-end callbacks |
| `rewrite_gate.py` [A\|R] (`--positive-only`) | `add_rewrite_rule`/`apply_rewrite_rules` |
| `inline_gate.py` [A\|R] | StaticHandler inline content-type/boundary/path/error bodies |
| `dispatch_gate.py` [A\|R] | Route/index/proxy-init/status bodies, TLS status buffer |
| `locale_gate.py` | Case-insensitive helpers against libc `strncasecmp` across available locales |
| `cookie_flow_gate.py` [A\|R] (`--status-only`, `--codes-only`) | Cookie callback flow; status fallback buffer; public `int[128]` status-code array export |
| `request_lifecycle_gate.py` [A\|R] | Request multipart init/destroy/destructor |
| `request_v2_model.py` [A\|R] | RequestV2 metadata through the facade and Rust owner |
| `context_gate.py` [A\|R] | Static context/serve-path controls |
| `boundary_rng_gate.py --export DIR` | Random-boundary overloads against a production corebase export; verifies the export's archive/header/source checksums first |

Locale semantic runs must be unsanitized: under ASan the macOS interceptor
compares `C0`/`E0` with ASCII rules where libc in `en_US.ISO8859-1` treats them
as equal. Unavailable locales are reported as unsupported.

## SDK/layout compile checks

These compile the real pinned and patched headers/translation units (no
`--archive`) and fail on layout, trait or syntax changes:

- `directory_compat.py [--standard c++14 --standard c++17]`: legacy
  StaticHandler data declarations, layout and copy/reference traits; V2
  composition. The default also tests C++20, which fails on the pinned
  process-pool volatile increment under `-Werror`.
- `request_v2_compat.py [--upstream-unused-parameter-policy]`: C++14/17 syntax
  for legacy, HTTP-only, PORTS-only and paired RequestV2 modes.

## PHP checks

These take `--engine NAME=/abs/swoole.so` (first `upstream=`), optional
`--php`/`--php-extension`, and `--output`.

- `binding_reflection.py`: class/method metadata of five HTTP PHP classes
  must equal the upstream engine.
- `static_server.py`: real local PHP HTTP server (16 requests: file bytes,
  percent/query paths, rewrite, ranges and multipart ranges, If-Range, HEAD,
  304, index, autoindex, 404, dynamic fallback) over one keep-alive socket;
  multiple engines also compare response fingerprints (excluding `Date`).
  `--measure --requests N --repeat N` times it; only run that on an otherwise
  idle host.
- `multipart_server.py`: successful streaming uploads (98 KiB file, two-file
  requests exceeding the 128 KiB total) checking field values and uploaded file
  SHA256s.
- `locale_server.py`: static location matching under explicit worker locales
  (binary prefixes, Turkish `I`/`i`).
- `request_splits.py --source PINNED_GIT`: deterministic sweep of all 501 cuts
  of the first request in `create_request.phpt` (pinned checksum verified).

### Original PHPTs

`upstream.json` is a manifest of 30 curated pinned PHPTs plus support blobs.
`full_originals.py --source PINNED_GIT [--group swoole_http_server_coro] --output M.json`
generates a manifest of the complete `tests/swoole_http_server` (138 cases) or
coroutine server (56 cases) tree. Run either with the official runner:

```sh
python3 corpus/upstream/run.py --source /path/to/phpized/pinned/source \
  --manifest target/http-check/full-originals.json \
  --engine upstream=/abs/reference.so --engine hybrid=/abs/candidate.so \
  --isolate-cases --timeout 90 --output target/http-check/full-originals-report.json
```

Linux minimal PHP needs `--php-extension sockets curl mbstring posix` (one flag
each). On macOS use `TMPDIR=/tmp` so the original Unix socket path fits, and the
run uses fixed `/tmp` fixtures (`swoole.log`, `client_ca.txt`, `sendfile.txt`,
`unix-sock-test.sock`), so do not run two at once.

## Benchmark preparation

`path_bench.py`, `proxy_bench.py [--positive-only]` and `index_page_bench.py`
take `--source --archive --binary --output`. Preparation compiles `-O3 -DNDEBUG` consumers,
verifies linked Rust symbols and runs an untimed check. Timing is
`BINARY --measure ENGINE WORKLOAD ITERATIONS` and must run on an idle host with
an optimized, uninstrumented archive. No timings have been recorded.

## Known failures

- `create_request.phpt`: random cookie-fragment defect in the untouched PHP
  request callbacks, not the Rust cookie iterator. `ext-src/swoole_http_request.cc`
  passes each llhttp header-value fragment to native `treat_data(PARSE_COOKIE)`
  separately, so a cut inside the Cookie value yields four cookies instead of
  three. `request_splits.py` reports 67 of 501 cuts failing (524-529, 532-533,
  535-541, 545-552, 554-590, 594-600) identically on both engines and exits 1.
- `If_Modified_Since.phpt` fails on macOS for native and hybrid (200 instead of
  304), consistent with a libc calendar offset difference.
- Full originals also fail or are unsupported for reasons outside Rust: the
  runner's unsupported custom `EXPECTF_85` section, zstd-disabled builds, missing
  `ip` executable (`server_addr`), `bug_2444` (needs MySQL), `tmp-content-type`
  (needs Composer Guzzle), coroutine `close_socket` (needs external HTTPS), and
  timeouts in `sendfile_client_reset`/issue 2360 (the original can stall waiting
  for more than 2 MiB from a randomly smaller file).
- `boundary_rng_gate.py` covers only the positive 24-byte length.
- RequestV2's capability stays off pending paired callers. Mixed Rust/native ASan
  linking fails on macOS.
