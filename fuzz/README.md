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
unchanged, copied by `crates/oracle/build.rs`. Two upstream behaviours are
excluded: `decode` reads two bytes even from shorter input, and a payload
within a header of `isize::MAX` overflows its signed length sum (Rust returns
-1).


For HTTP, `http_url_decode`, `http_url_encode` and `http_cookies` (keys and
values in order) compare with upstream's `url_decode`, `url_encode` and
`parse_cookie`. The shim gives each upstream `sw_malloc` one spare byte, because
`url_encode` writes past its allocation (#145).


For packet framing (`open_length_check`), `framing_unpack` compares
`swr_v1_framing_unpack` with `swoole_unpack` for every length type, and
`framing_length` compares `swr_v1_framing_default` with
`Protocol::default_length_func` over a length type, field offset, body offset and
any received bytes. A body length within the body offset of `INT64_MAX`
overflows upstream's signed sum; there Rust's -1 only has to match an upstream
error.

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
   seeds in `seeds/<name>/` taken from the crate's exhaustive tests, and the
   target to the `fuzz` job in `.github/workflows/merge.yml`.
