# Wrapper validation

The wrapper area is `src/wrapper/event.cc` and `src/wrapper/http.cc` (timer.cc
belongs to the timer module). Rust owns HTTP request/multipart field names and
byte accumulation, completion policy, URL/listener splitting, header
classification, response-header serialization, Content-Length digits, response
send sequencing, event direction/wait admission and event-init ordering. Native
code keeps the public `Context` containers, C++ resource lifetimes, callbacks,
transport, llhttp/multipart parsers, FILE/tmpfile handling and warnings. See
[native/wrappers/contract.md](../../../native/wrappers/contract.md).

`overlay.py` generates the patched `event.cc`/`http.cc` from the pinned
upstream sources; run it directly to rewrite `migration/patches/wrappers/`.

## Registered gates

- `gate.py --archive FFI_ARCHIVE --output R [--sanitize] [--rust-asan]`
  (`wrappers-native`): ABI consumer (`gate.cc`) with 20,000 seeded snprintf
  differentials, request/multipart/header policy, null/empty/binary/truncation
  inputs, duplicate parameters, threads, fork and destruction. `--rust-asan`
  also requires an instrumented archive to detect a deliberate one-past read.
- `listener.py` and `response.py`, both
  `--source PINNED --archive A --output R [--core CONFIGURED_SRC] [--include DIR] [--sanitize] [--rust-asan]`
  (`wrappers-listener`, `wrappers-response`): extract the pinned and patched
  method bodies, compile them into a model driver and compare them (listener:
  8,213 address-prefix/ABI cases; response: 5,760 `Context::end` traces plus
  16,392 Content-Length decimal comparisons). With `--core`, all four
  original/patched event/http translation units are syntax-checked against the
  configured SDK.
- `upstream.py --source S --engine name=swoole.so ...` (`wrappers-originals`):
  all pinned `tests/swoole_event` and `tests/swoole_timer` PHPTs through PHP's
  official runner.

## Other gates

- `disposition.py` and `event_init.py` take the same arguments as
  `response.py` and reuse its runner with a different extracted body:
  multipart header-value disposition decoding (41,025 cases) and
  `swoole_event_init` ordering/admission (16,436 cases).
- `core.py --source S --config CONFIG_H --archive A --build-root DIR --output R [--library-only] [--openssl-root P]`:
  builds upstream and wrappers-only native trees with CMake and runs the
  unchanged reactor/timer GTests and the four HTTP wrapper tests (parser1,
  parser2, upload, max_request_size) one process each. `--library-only` builds
  the libraries without running tests (used by the next three scripts).
- `native.py --core-root DIR --output R [--openssl-root P]`: loopback
  Server/Context/SyncClient application against both native libraries,
  comparing response bytes, public maps, form/file content and file cleanup
  over five scenarios. Each run verifies the loaded library path and hash.
- `diagnose.py --source S --core-root DIR --observations NATIVE_REPORT --output R`:
  same scenarios with the reference's two uninitialized pointers initialized;
  must match the Rust observations from a `native.py` report.
- `fdopen.py --source S --core-root DIR --output R --scenario stream|map-registration|success|write|short-write [--fail-at N]`:
  multipart upload callbacks with faults injected at fdopen, map-registration
  allocation and fwrite; checks fd closure, temp-file removal, errno and the
  files map.
- `disposition_loaded.py --selected EXPORT_DIR --output R [--php P] [--ffi-extension FFI_SO]`:
  calls the loaded DSO's disposition function via PHP FFI (1,216 cases); the
  DSO must match `export.json`.
- `header_transfer_model.py --core CONFIGURED_SRC --output R [--include DIR]`:
  test-only Rust ordered-header store handing off into the real public
  `std::unordered_map`, built as C++14 and C++17 under ASan/UBSan.
- `sockets_build.py --output R --module wrappers --dev --jobs 2` (or
  `--backend upstream --dev --jobs 2`): runs the shared hybrid builder with
  `--enable-sockets` and checks `SW_SOCKETS` is defined.
- `benchmark.py --prepare DIR --core-root CORE [--openssl-root P]`, then
  `benchmark.py --prepared DIR [--output R]`: event add/update consumer.
  Preparation verifies loaded images without reading the clock; `--prepared`
  times five alternating trials. Run timings with no other workload.
- `python3 -m unittest tests/modules/wrappers/test_model_checkpoints.py`:
  Python-only test of the `response.py` runner's partial-report checkpoints.

Example:

```sh
python3 tests/modules/wrappers/response.py --source target/upstream/src \
  --archive target/.../libswoole_rs_ffi.a --core target/.../src \
  --include /dependency/include --sanitize --output target/reports/response.json
```

## Known failures

- `native.py`: the pristine reference SIGSEGVs on the GET, empty-query and
  urlencoded-form scenarios (uninitialized `mt_parser`/`form_data_buffer` in
  upstream `ContextImpl`); multipart and file pass and match Rust. The paired
  gate fails. `diagnose.py` shows all five match Rust once those pointers are
  initialized.
- `core.py` on macOS: the upstream HTTP test unit uses Linux `stat.st_mtim`
  and does not compile; only `--library-only` works there.
- `upstream.py`: four timer cases (`bug_4794_3/5/6/7`) need external network
  and are excluded unless `--external-network`, and the gate fails while any
  case is excluded. `swoole_event/sockets.phpt` fails in both engines unless
  the extension is built with `--enable-sockets` (see `sockets_build.py`); the
  combined all-module build does not enable it.
- On Linux Docker bind mounts, libtool's install copy can fail with
  `error deallocating ... Invalid argument`; a PATH `cp` shim passing
  `--sparse=never --reflink=never` works around it.
