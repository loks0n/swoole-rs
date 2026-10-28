# String gates

ABI and semantics: `native/buffer/string-contract.md`. All commands run from the
repository root; `S` is the pinned upstream checkout and `A` a Rust archive.

## Native profiles: `test_gate.py`

```sh
python3 -m pytest tests/modules/buffer/string/test_gate.py --archive A --sanitize   # reads target/upstream/src
python3 -m pytest 'tests/modules/buffer/string/test_gate.py::test_profile[format]' --archive A --sanitize
```

`tools/dev.py` runs each profile as the phase `string-<profile>`. Each compiles
pinned `string.cc`, `base.cc`, `os/base.cc` and `base64.cc` (`string_build.py`)
for upstream and for the patched Rust engine, checks the Rust symbols in the
linked binary and runs the consumer.

| Profile | Checks |
| --- | --- |
| `originals` | All 23 tests of byte-identical pinned `core-tests/src/core/string.cpp`, with exact test-ID inventory and zero failures. |
| `ownership` | 13 assignment/destructor metadata and custody checks; selected adds 3 origin checks. |
| `allocation` | 12 constructor/reserve metadata checks, including caught reserve OOM. |
| `format` | 604 checks over all append/grow flag combinations, capacity, terminator, empty sizing, binary output and caught OOM. |
| `random` | 673 checks of 1..1024-byte raw/Base64 random appends, with an OpenSSL decode. |
| `integer` | Integer append with standard/custom allocators, signed limits, spare/full capacity and caught realloc failure. |
| `transitions` | clear/move/release/terminate transitions on custom-owned allocations (71 checks). |
| `copy` | Copy/provenance and caught constructor OOM. |
| `split` | Callback continuations: false/throw offsets, reallocation, future-byte mutation, binary residuals. |

`--rust-asan` declares an ASan-instrumented archive (see `../README.md`).
`test_gate.py` then requires the native sanitizer and the archive's ASan imports.

## Compatibility step: `compatibility.py`

```sh
python3 -m pytest tests/modules/buffer/string/test_compatibility.py --archive A --sanitize   # reads target/upstream/src
```

Ordinary append/write/i32/repeat/copy/termination/reduce, 44 checks per engine,
plus C11 layout asserts and selected whole-TU syntax under C++14/17/20.
The output path must not exist.

## Benchmark: `benchmark.py`

```sh
python3 tests/modules/buffer/string/benchmark.py --prepare DIR --archive A --output P.json
python3 tests/modules/buffer/string/benchmark.py --prepared-report P.json \
  [--previous-prepared-report PREV.json] [--workloads ...] --repeat 9 --iterations 30000 --output R
```

`--prepare` compiles optimized consumers into DIR and checks every workload
untimed; the second form times them, after checking their binary hashes. Run only on an idle host. Results: [algorithms.md](algorithms.md).

## Known failures

- `random` covers lengths 1..1024 only. Native zero-length encoded random
  append fails its exact-length assertion.
