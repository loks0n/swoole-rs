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
python3 tests/modules/buffer/string/compatibility.py --source S --archive A --sanitize [--direct-fields] --output R
```

Ordinary append/write/i32/repeat/copy/termination/reduce, 44 checks per engine,
plus C11 layout asserts and selected whole-TU syntax under C++14/17/20.
`--direct-fields` also checks the `SWOOLE_RS_STRING_DIRECT_FIELDS` refusals.
The output path must not exist.

## Loaded PHP consumers: `production.py`

```sh
python3 tests/modules/buffer/string/production.py \
  --source S --source-ref SELECTED_COMMIT \
  --engine native=/abs/native/swoole.so --engine selected=/abs/selected/swoole.so \
  --build-manifest /abs/selected/build-manifest.json --archive A \
  --selected-export /abs/selected/export.json --native-export /abs/native/export.json \
  --consumer CONSUMER --output R
```

Builds a small PHP addon against headers reconstructed from each build's pinned
inputs and patches; it links no String implementation or Rust archive. `nm`
must show the addon importing the production methods and `dladdr` must resolve
them inside the loaded extension. Consumers: `random`, `compatibility`, `format`,
`allocation`, `ownership`, `integer`, `split`, `copy`, `facade`, `storage`,
`metadata`, `terminator`, `iovec`. Native and selected assertion counts must
match. `--borrow-immutable-exports` uses the export `swoole.so` in place instead of
copying it, and verifies the export files are unchanged before and after the run.
`--require-direct-fields` applies to the `compatibility` consumer. Optional
`--php`, `--php-config` and `--php-extension` select the PHP SDK.

`tests/modules/coroutine/production_stack.py` and
`tests/modules/reactor/production_supported.py` import its header helpers.

## System allocator: `system-allocator.py`

```sh
python3 tests/modules/buffer/string/system-allocator.py --source S --archive A --directory /abs/new/dir
```

Interposes malloc/calloc/realloc/free (`DYLD_INSERT_LIBRARIES` or `LD_PRELOAD`,
test child only) and runs 24 fresh-process scenarios per engine: cold growth
trace (malloc 64, realloc 256..4096, free), failure at each growth, constructor
malloc failure, calloc, realloc(NULL), disjoint interior append and zero-size
cases. Rust adds two alias-rebase scenarios. Failed growth must keep pointer,
length, offset, capacity and bytes.

The report exits 1 on purpose: native String has two zero-owner defects, so
native passes 23/24 on macOS and 22/24 on Linux (Rust 26/26).

- `String(0).reserve(16)` loses its `malloc(0)` owner on both hosts.
- On Linux, `reserve(0)` frees through `realloc(p, 0)`, gets null and throws with
  a dangling pointer.

## Benchmark: `benchmark.py`

```sh
python3 tests/modules/buffer/string/benchmark.py --prepared-report P.json \
  [--previous-prepared-report PREV.json] [--workloads ...] --repeat 9 --iterations 30000 --output R
```

Times consumers prepared by `gate.py --prepare-benchmark`, after checking their
binary hashes. Run only on an idle host. Results: [algorithms.md](algorithms.md).

## Known failures

- `production.py --consumer random` covers lengths 1..1024 only. Native
  zero-length encoded random append fails its exact-length assertion.
- Native DATA destroy callbacks on freed bytes are not exercised by the facade
  consumer.
- `test_gate_profiles.py` and `test_production.py` are unit tests that need no build.
