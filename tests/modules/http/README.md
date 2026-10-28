# HTTP checks

The HTTP module moves first-party helpers, request/header/chunk framing, cookies,
proxy policy, static paths/ranges/headers/calendar/rewrite/index rendering and
multipart accounting into Rust; it is graduated (always on). Native code keeps PHP and
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
| `multipart_emit_gate.py` [A\|R] | Header-complete/data-end/part-begin/body-end callbacks |
| `rewrite_gate.py` [A\|R] (`--positive-only`) | `add_rewrite_rule`/`apply_rewrite_rules` |
| `inline_gate.py` [A\|R] | StaticHandler inline content-type/boundary/path/error bodies |
| `dispatch_gate.py` [A\|R] | Route/index/proxy-init/status bodies, TLS status buffer |
| `locale_gate.py` | Case-insensitive helpers against libc `strncasecmp` across available locales |
| `cookie_flow_gate.py` [A\|R] (`--status-only`, `--codes-only`) | Cookie callback flow; status fallback buffer; public `int[128]` status-code array export |
| `request_lifecycle_gate.py` [A\|R] | Request multipart init/destroy/destructor |
| `context_gate.py` [A\|R] | Static context/serve-path controls |
| `boundary_rng_gate.py --export DIR` | Random-boundary overloads against a production corebase export; verifies the export's archive/header/source checksums first |

Locale semantic runs must be unsanitized: under ASan the macOS interceptor
compares `C0`/`E0` with ASCII rules where libc in `en_US.ISO8859-1` treats them
as equal. Unavailable locales are reported as unsupported.

## SDK/layout compile checks

These compile the real pinned and patched headers/translation units (no
`--archive`) and fail on layout, trait or syntax changes:

- `directory_compat.py`: legacy StaticHandler data declarations, layout and
  copy/reference traits; V2 composition, under C++14 and C++17. C++20 fails on
  the pinned process-pool volatile increment under `-Werror`.

## PHP checks

These take `--engine NAME=/abs/swoole.so` (first `upstream=`), optional
`--php`/`--php-extension`, and `--output`.

- `binding_reflection.py`: class/method metadata of five HTTP PHP classes
  must equal the upstream engine.

### Original PHPTs

Upstream PHPTs for this module run in the merge tier's PHPT gate (the `phpt-*` jobs), which runs every pinned PHPT on upstream and the all-modules hybrid. To attribute a gate regression to this module, see *Attributing a regression* in [corpus/upstream/README.md](../../../corpus/upstream/README.md).

## Benchmark preparation

## Known failures

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
