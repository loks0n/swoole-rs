# M18 framing and MIME

Packet framing and the immutable MIME policy behind the optional framing feature
(bit4096). The native C++ container and the native IO/callback/storage ABI shims
are described in [native/framing/contract.md](../../../native/framing/contract.md).
Default activation is not claimed.

## Gates

`tools/dev.py` runs `gate.py` (framing-native), `trace.py` (framing-traces) and,
.

```sh
mkdir -p target/reports
python3 tests/modules/framing/overlay.py   # regenerate migration/patches/framing
python3 tests/modules/framing/trace.py --output target/reports/framing-trace.json
rustc --edition=2024 --crate-type=staticlib --crate-name swoole_rs_framing \
  -O -Dwarnings crates/framing/src/lib.rs -o target/libframing.a
python3 tests/modules/framing/gate.py --archive target/libframing.a \
  --sanitize --output target/reports/framing-gate.json
```

- `trace.py` compiles the exact pinned C++ bodies and the generated callers
  against instrumented IO/String boundaries and compares the traces line by
  line. The traces cover partial packets, split residuals, callback
  failure/removal ordering, reentry, TLS pending, allocation exceptions and
  dynamic-header offset/body/header_len ordering.
- `gate.py` runs the ABI, catalog, locale-suffix and malformed-input checks in
  `gate.cc`. Add `--rust-asan` with an instrumented archive to also require
  that a one-past read in the invalid caller is detected.
- `core.py --source S --config config.h --archive A --build-root DIR --output R`
  needs Linux with CMake, GTest and PHP. It builds the unchanged pinned native
  GoogleTests for the reference and the framing overlay, and runs each test
  separately. Any error, skip or missing outcome fails. `--inventory-only`
  lists the tests without building.
- Upstream PHPTs for this module run in the merge tier's PHPT gate (the `phpt-*` jobs), which runs every pinned PHPT on upstream and the all-modules hybrid. To attribute a gate regression to this module, see *Attributing a regression* in [corpus/upstream/README.md](../../../corpus/upstream/README.md).
- `expectation_diagnostic.py --source S --engine NAME=SO ... --output R` is an
  adapted diagnostic, not an original gate. It runs `wrong_eof_setting.phpt`
  with its version-specific expectation selected: EXPECTF on PHP 8.2,
  EXPECTF_85 on PHP 8.5. The FILE, SKIPIF and expectation bodies stay
  byte-identical. PHP 8.5 needs `--runner-fatal-backtraces`. Use
  `--official-runner` when the source is mounted from another host.
- `mime_loaded.py --source S --native DIR --selected DIR --output R` loads two
  exported `swoole.so` builds into PHP. It compares the 362-entry catalog, 735
  lookup/exists pairs and 17 add/set/delete observations, including upper-case
  suffixes, last/no/trailing dot, fallback and first-NUL truncation.
- `mime_memory.py --source S --configured-root DIR --archive A --output R`
  compares original and Rust MIME lookup under a per-allocation byte ceiling
  (`--allocation-ceiling`, default 128; 0 means uncapped).
- `mime_suffix_plan.py --source S --core DIR --archive A --output R` compiles
  the original and selected MIME translation units with ASan/UBSan. It checks
  seven get cases and 8193 Rust suffix-offset cases, then syntax-checks
  base/MIME against the SDK (`--include` adds include paths).
- `benchmark.py --prepare DIR --core-root ROOT` compiles the native consumers
  and runs an untimed `check` for both engines. `benchmark.py --prepared DIR`
  then runs five alternating trials each of length dispatch, EOF split (8-byte
  and 64KiB packets), MIME lookup and unpack. Benchmarks need an idle host.
  IO, PHP and whole-server throughput are excluded. No measurements have been
  recorded.

## Known failures

- PHP originals: macOS has 43 pass, 2 skip and 2 fail; Linux has 45 pass,
  1 skip and 1 fail. Both engines get the same results.
- `wrong_eof_setting.phpt` fails on both platforms. The official PHP runner
  treats upstream's custom EXPECTF_85 marker as literal expected text.
  `expectation_diagnostic.py` passes in both engines.
- On macOS, `If_Modified_Since.phpt` returns 200 instead of 304 in both engines.
- The SMTP online test skips. macOS also skips the Linux-only large-packet test.
- Under the 128-byte allocation ceiling, both engines throw for a 1MiB filename
  prefix, because the reference copies the whole filename too. This is not a
  migration regression. The uncapped control matches on both platforms.
- Linux validation of `mime_loaded.py` and `mime_suffix_plan.py` has not run.
- Still open: optimized measurements, broader platform/feature/combined
  activation, and the remaining original failures.
