# Differential fuzzing

Each target feeds the same bytes to a Rust `swr_v1_*` export and to the pinned
upstream C++ in `crates/oracle`, and fails on any difference in the return value
or any output byte. `cargo fuzz` builds both sides with ASan, so a memory error
in either is a crash too. The workspace stays on its pinned stable toolchain;
fuzzing needs nightly:

```sh
rustup toolchain install nightly --profile minimal
cargo +nightly install cargo-fuzz --locked
cd fuzz
mkdir -p corpus/base64_decode
cargo +nightly fuzz run base64_decode corpus/base64_decode seeds/base64_decode -- -dict=base64.dict -max_total_time=60
```

Targets: `base64_decode`, `base64_encode`, and for the WebSocket codec
`ws_decode` (any bytes as one frame: verdict, fields and in-place unmasking),
`ws_frame_length` (total and header length of any prefix) and `ws_mask` (first
four bytes as the key; masking twice restores the data). The WebSocket oracle
compiles upstream's `get_package_length_impl`, `mask` and `decode` bodies
unchanged, copied by `crates/oracle/build.rs`. Inputs where upstream's behaviour is undefined (private advisory) are
excluded from comparison; Rust's result is still checked.


For HTTP, `http_url_decode`, `http_url_encode` and `http_cookies` (keys and
values in order) compare with upstream's `url_decode`, `url_encode` and
`parse_cookie`. The shim gives each upstream `sw_malloc` one spare byte, so
upstream runs to completion where its behaviour is undefined (private advisory).


For HTTP request framing, `http_frame` runs `get_protocol`, `get_header_length`
or `get_chunked_body_length` from a chosen offset, header length and request
state, and `http_header` runs `has_expect_header`, `get_header(name)` and
`get_method_string`. Both compare the pinned http.cc bodies with the same bodies
after `migration/patches/http/0001-http-helpers.patch` (which call Rust), over a
`Request` with upstream's field types, copied by `crates/oracle/build.rs`. Inputs
where upstream's behaviour is undefined (private advisory) are excluded from comparison; the candidate is still checked. Seeds include the requests
`http.client` sends for the corpus applications.

For MQTT and RESP, `mqtt_length` compares `mqtt::get_package_length` over any
received bytes and `resp_parse` compares `redis::parse` (every string and, on
glibc, `ERANGE`), each against the same body after
`migration/patches/protocols/0001-rust-packet-protocols.patch`. Where upstream's behaviour is undefined (private advisory), only the candidate runs: `resp_parse` models upstream's walk
without reading memory to find those inputs.

For packet framing (`open_length_check`), `framing_unpack` compares
`swr_v1_framing_unpack` with `swoole_unpack` for every length type, and
`framing_length` compares `swr_v1_framing_default` with
`Protocol::default_length_func` over a length type, field offset, body offset and
any received bytes. Where upstream's behaviour is undefined (private advisory), Rust's -1 only has to match an upstream error.

libFuzzer writes new inputs to the first corpus directory, so keep `corpus/`
(ignored) first and the committed `seeds/` second. A failure leaves its input in
`artifacts/<target>/`; replay it with `cargo +nightly fuzz run <target> <file>`.
On Linux, build with `CC=clang CXX=clang++` so the C++ ASan matches rustc's.

## Adding a target

1. Declare the upstream function in `crates/oracle/src/lib.rs` and compile its
   unmodified source in `crates/oracle/build.rs` (through `cpp()`).
2. Add a comparison to `src/lib.rs`: call both sides on the same input, with
   red zones around each output, and assert on the returns and the bytes.
3. Add `fuzz_targets/<name>.rs` calling it, a `[[bin]]` in `Cargo.toml`, a few
   seeds in `seeds/<name>/` taken from the crate's exhaustive tests. A
   `<prefix>.dict` named after the target's first word is picked up too.

## CI

ClusterFuzzLite (`.clusterfuzzlite/`) builds every target. On PRs touching
`crates/`, `fuzz/` or `.clusterfuzzlite/`, it fuzzes the targets the change reaches
for five minutes (`cflite_pr.yml`). Nightly it fuzzes all targets for an hour
and then prunes its stored corpus (`cflite_batch.yml`). A crash fails the run,
and the minimised input is uploaded as `cflite-crashes`.
