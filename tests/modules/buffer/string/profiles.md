# String gates

ABI and semantics: `native/buffer/string-contract.md`. All commands run from the
repository root; `S` is the pinned upstream checkout and `A` a Rust archive.

## Native profiles: `gate.py`

```sh
python3 tests/modules/buffer/string/gate.py --source S --archive A --sanitize PROFILE --output R
```

Exactly one profile is required. Each compiles pinned `string.cc`, `base.cc`,
`os/base.cc` and `base64.cc` for upstream and for the patched Rust engine, checks
the Rust symbols in the linked binary and runs the consumer.

| Profile | Checks |
| --- | --- |
| `--original-only` | All 23 tests of byte-identical pinned `core-tests/src/core/string.cpp`, with exact test-ID inventory and zero failures. |
| `--ownership-only` | 13 assignment/destructor metadata and custody checks; selected adds 3 origin checks. |
| `--allocation-only` | 12 constructor/reserve metadata checks, including caught reserve OOM. |
| `--format-only` | 604 checks over all append/grow flag combinations, capacity, terminator, empty sizing, binary output and caught OOM. |
| `--random-only` | 673 checks of 1..1024-byte raw/Base64 random appends, with an OpenSSL decode. |
| `--integer-only` | Integer append with standard/custom allocators, signed limits, spare/full capacity and caught realloc failure. |
| `--transition-only` | clear/move/release/terminate transitions on custom-owned allocations (71 checks). |
| `--copy-only` | Copy/provenance and caught constructor OOM. |
| `--split-only` | Callback continuations: false/throw offsets, reallocation, future-byte mutation, binary residuals. |
| `--prepare-benchmark DIR` | Compiles optimized consumers into DIR and runs untimed workload checks. |

`--rust-asan` declares an ASan-instrumented archive (see `../README.md`).

## Compatibility step: `compatibility.py`

```sh
python3 -m pytest tests/modules/buffer/string/test_compatibility.py --archive A --sanitize   # reads target/upstream/src
```

Ordinary append/write/i32/repeat/copy/termination/reduce, 44 checks per engine,
plus C11 layout asserts and selected whole-TU syntax under C++14/17/20.
The output path must not exist.

## Benchmark: `benchmark.py`

```sh
python3 tests/modules/buffer/string/benchmark.py --prepared-report P.json \
  [--previous-prepared-report PREV.json] [--workloads ...] --repeat 9 --iterations 30000 --output R
```

Times consumers prepared by `gate.py --prepare-benchmark`, after checking their
binary hashes. Run only on an idle host. Results: [algorithms.md](algorithms.md).

## Known failures

- `--random-only` covers lengths 1..1024 only. Native zero-length encoded random
  append fails its exact-length assertion.
- `test_gate_profiles.py` is a unit test that needs no build.
