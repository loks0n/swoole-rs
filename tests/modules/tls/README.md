# TLS validation

Rust owns the TLS/DTLS setup policy, BIO read/control/listen decisions, info
callback actions and password-callback copy rule (`swr_v1_tls_context`,
`setup`, `read`, `control`, `listen`, `password`). Native code keeps callbacks,
the global SSL authority, OpenSSL objects and public storage.

## differential.py

Compiles the complete pinned and patched `src/protocol/ssl.cc` and `dtls.cc`
into a driver, links both against one matching native full-core library and
compares their output. The patched tree gets its own Git root so `git apply`
cannot be silently skipped; the patched driver must contain definitions and
call instructions for all six Rust functions, the reference none. Loader
output, the native library and the loaded libssl/libcrypto are checked to be
unchanged across the run.

```sh
python3 tests/modules/tls/differential.py --reference PINNED_GIT \
  --source CONFIGURED_HEADER_TREE --library NATIVE_LIBSWOOLE \
  --openssl OPENSSL_PREFIX --output R [--archive FFI_ARCHIVE] [--sanitize] \
  [--gtest-prefix PREFIX] [--peers | --allocation | --crypto-allocation | --benchmark-check]
```

- default (`driver.cc`): 256 context masks x 2 compression flags, encrypted
  cert/key/passphrase setup and native setup failures (missing cert/key/CA,
  invalid cipher/curve, wrong passphrase, DH and curve variants), 40 BIO
  length/request/peek cases and the four expected unknown-command warnings.
  Only the logger's timestamp/PID prefix is normalized.
- `--gtest-prefix`: also builds unchanged upstream
  `core-tests/src/protocol/ssl.cpp` with `original_main.cc` and runs
  `ssl.destroy`, `ssl.get_error`, `ssl.password` one process each.
- `--peers` (`peers.cc`): in-memory TLS 1.2/1.3 peers (trust, hostname, ALPN,
  password callback, DHE/ECDHE, data, two-sided shutdown), DTLS over an
  AF_UNIX datagram pair with cookie generation/verification and
  `Session.listen`, native re-init cycles, four native threads, info callback
  events and fork.
- `--allocation` (`allocation.cc`): replaceable C++ `operator new` failures
  through the native warning formatters and the DTLS `BIO_ctrl` callback.
- `--crypto-allocation --crypto-operation client-ca|dhparam|curve|dtls-init`
  (`crypto_allocation.cc`): OpenSSL allocator-hook single-failure sweep.
- `--benchmark-check --archive A` (`benchmark.cc`): prepares six fixed optimized
  workloads and verifies their checksums without timing anything.
- `--sanitize` adds ASan/UBSan to the native TUs and driver only (not Rust, the
  native DSO or OpenSSL); leak detection is off.

## gate.py (registered as `tls-native`)

```sh
python3 tests/modules/tls/gate.py --source PINNED_GIT --config SELECTED_CONFIG_H \
  --archive SELECTED_FFI --output R --jobs N [--gtest-prefix PREFIX] \
  [--native-report REPORT] [--allocation-native-report REPORT]
```

Runs `differential.py` against the supplied FFI archive in three children:
sanitized setup with original GTests, sanitized peers, and ordinary
allocation. It first checks the archive exports ABI 1 with TLS feature bit
262144 and that the public headers match the pin. It never builds a native
runtime: the native library comes from an existing successful build report
(the coroutine `core.py` report, a `tools/native_core.py` report, or a corebase
outer report wrapping one) whose library and compiled config must match.
Without `--native-report` it tries `coroutine-native-originals.json` next to
the output. The allocation child needs an uninstrumented native library; if
the main control has sanitizer symbols, pass `--allocation-native-report`.

## php.py

Runs the unchanged local TLS/DTLS PHPTs listed in `php-local-cases.json`
(default) or `php-verification-cases.json` against a published export
(`swoole.so`, `reference.so`, `libswoole_rs_ffi.a`, `build-manifest.json`),
after checking the export hashes, the PHP SDK against the build manifest, and
that the selected extension calls every TLS export while the reference calls
none. Linux only (uses `ldd`/`objdump`).

```sh
python3 tests/modules/tls/php.py --source PINNED_GIT --artifacts EXPORT_DIR \
  --runner MATCHING_SDK_RUN_TESTS_PHP --manifest tests/modules/tls/php-verification-cases.json \
  --dh-witness --output R [--container-inspect INSPECT_JSON] \
  --php-extension pdo --php-extension pdo_sqlite --php-extension curl \
  --php-extension sockets --php-extension tokenizer --php-extension posix --php-extension mbstring
```

`--dh-witness` adds `php-dh.phpt` (DHE server with the pinned DH params at
security level 0); `--dh-witness-only` runs just that.

## Unit tests

```sh
python3 -m unittest tests/modules/tls/test_gate.py tests/modules/tls/test_php.py
```

Python-only checks of `gate.py` control-report acceptance, `differential.py`
argument guards and timeout handling, and `php.py` export parsing.

## Known gaps and failures

- Upstream `ssl.password` uses an uninitialized `SSLContext`; it passes, but on
  undefined input.
- `verify_02` has been observed WARNED (flaky) in the PHP cohort.
- An empty curve list is accepted by OpenSSL 3.6 and rejected by 3.0; the
  curve fixture probes OpenSSL directly rather than hard-coding either.
- A native library built without DTLS/listen would fail the six-caller check;
  there is no capability handling for that yet.
- Not covered: real IP sockets, packet loss, PHP cancellation, legacy/no-ECDH
  OpenSSL configurations, PHP coverage of the curve/info/session/password
  conversions, macOS PHP runs and performance.
