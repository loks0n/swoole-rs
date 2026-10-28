# M26 common PHP helpers and optional stdext

M26 covers `ext-src/php_swoole_cxx.cc`, `ext-src/swoole_stdext.cc` and the
String/KeyValue/ArrayIterator/Array/Variable/CharPtr/inline Callable methods and
callable factories in `ext-src/php_swoole_cxx.h`. Public declarations, layout and
macros stay frozen. The contract is
[docs/phphelpers-abi-v1.md](../../../docs/phphelpers-abi-v1.md).

Rust owns copied-scalar policy. Native Zend storage, HashTables/COW/GC, VM
frames, allocators/destructors, autoload/callbacks/coroutines, exceptions/
bailouts and SAPI/PCRE/JSON execution stay native. Rust returns before every
effect, keeps no native borrow across reentry and has no duplicate mutable
registry.

| Rust policy | Native effects and representation |
| --- | --- |
| 151 immutable aliases, argument ranges, 11 wrapper bindings | Native strings, argument buffers, cached functions and actual calls |
| Callable construction/release, keyed merge (index vs string route), bool/named call lifecycles | Values/refcounts, numeric-key classification, HashTable APIs, lookup, diagnostics and invocation |
| 64 known strings and 14-step stdext initialization | Persistent/interned pointer table, opcode/function caches, handler capture/replacement |
| Typed validation/mutation/VM/builtin/construction/predicate plans | Dereference, classes/COW, opcode frames, allocation/publication and cleanup |
| Definition parsing/projection, byte compaction, metadata equality | libc locale classification, lowercase/autoload, initialized spans and errors |
| Method frame/invocation, opcode/operation and JSON options | VM/class/cache access, scope/string guards and PHP libraries |
| PCRE cache/count/refcount/match/return sequencing | Parameter parsing, PCRE library, result zvals and PHP-version APIs |
| String/CharPtr/KeyValue/Variable/Callable custody and factories; one release decision per String/CharPtr teardown | Allocation/copy/move/refcounts, storage, callbacks, destruction and errors |
| ArrayIterator traversal; Array update status | Bucket bounds/kinds/indirection, cursor/key storage and HashTable updates |
| `php_swoole_async` admission (blocking short-circuit, one nonblocking context query) | `std::function` capture/storage, invocation, async/yield, exceptions/bailout |

Behaviour to preserve: unsigned-byte locale semantics, initialized type bytes
beyond NUL while comma lookup stops at NUL, original diagnostic spelling,
allocation/error/publication/cleanup order and fresh observations after
callbacks. Native dup is a C string; Zend edup keeps binary length. Removing the
alias map changes startup allocation/OOM behaviour.

Edit the three overlays with `tools/patches.py`; see
[hybrid build](../../../docs/hybrid-build.md#editing-patches).

## Body gate (`gate.py`, `phphelpers-policy`)

```sh
python3 tests/modules/phphelpers/gate.py --source PINNED --sanitize --output BODY.json
```

Runs complete pinned and selected bodies against modeled native storage and
effects, one fixture per family (`gate.cc`, `effects.cc`, `definition.cc`, ...):

| Family | Matched cases per host |
| --- | --- |
| Aliases / arguments | 151 known, 302 unknown, 2080 permutations |
| Validation / mutation / builtin wrappers | 22680 / 16384 / 25920 |
| Definition parse / initialized span | 324 Mac, 216 Linux / 120 Mac, 80 Linux across available locales |
| Typed VM / method frame / invocation | 40320 / 960 / 7200 plus 360 reorder cases |
| Typed construction / public predicate | 59904 / 208 |
| Known cache / Callable cleanup / registration | 266 / 12 / 80 |
| PCRE / generated library wrappers | 1296 across PHP 8.2/8.5 APIs / 55 across 11 wrappers |
| Empty predicates / String+CharPtr / KeyValue+Variable / inline Callable | 24 / 13 / 9 / 14 |
| ArrayIterator / Array updates | 4681 bounded walks / 2 status profiles |

These are modeled counts, not Zend runtime coverage. `--rust-sanitize` builds a
private ASan-instrumented Rust module; `--archive EXACT --sanitize --rust-asan`
instead checks ASan imports in a supplied archive. Rust std, Zend and system
libraries stay uninstrumented, and Rust ASan does not work on macOS.

`async_gate.py --source PINNED --output UNIQUE.json [--archive FFI.a]`
(`phphelpers-async`) runs the original and selected `php_swoole_async` bodies with
inert recorders (8 dispatch cases), the C11 `async_abi.c` consumer, and C++14/17
with and without ASan/UBSan. It checks the native fallback is unchanged.

## SDK compile checks

```sh
python3 tests/modules/phphelpers/sdk.py --source PINNED --sdk-export IMMUTABLE/export.json --output SDK.json
```

`sdk.py` (`phphelpers-sdk`) compiles 24 actual-TU profiles (native/M26-only/
combined x stdext off/on x two `.cc` files x C++14/17), checks seven class
size/alignment witnesses agree, compiles six optimized `php_swoole_async` caller
objects and checks their Rust imports. It also compares declarations outside 68
inline bodies and 10 verbatim macros against the pinned header. Missing optional
packages (for example libpq) keep their error but do not drop other flags. Its
report (per-command dependency hashes, `selected_header_sha256`, the native public
header hash) is the input for `entrypoint.py`, `facade_runtime.py`,
`async_optional_sdk.py`, `prepare_php_benchmark.py`,
`tests/modules/phpevents/` and `tests/modules/phpcoroutines/sdk.py`.

`async_optional_sdk.py --source PINNED --sdk-report SDK.json --provider sqlite|odbc
--output UNIQUE.json` compiles the unchanged optional SQLite or ODBC consumer TU
with its feature enabled (native/M26/combined x C++14/17, `-Werror`) and checks
the defined async wrappers and Rust imports. ODBC uses installed pkg-config flags
and an explicit unixODBC configuration. Nothing is linked or executed.

## Loaded PHP checks

All take `--engine native=DSO --engine selected=DSO`, `--build-manifest`,
`--archive` (`manifest.parent/'src/../rust-prefix/lib/libswoole_rs_ffi.a'`),
`--source-ref` and `--output`; Linux needs `--php-extension curl.so`.

- `runtime.py` (`phphelpers-runtime`): stdext copied arrays, native callbacks,
  autoload and object lifetime (`runtime.php`), plus `bailout.php` children for
  direct/coroutine return/exception.
- `entrypoint.py --sdk-report SDK.json` (`phphelpers-entrypoint`): builds a
  test-only extension from `entrypoint.cc` and checks named C++ entry results and
  child diagnostics (`entrypoint.php`, `entrypoint-child.php`).
- `facade_runtime.py --sdk-report SDK.json [--prepare-only]`
  (`phphelpers-facade-runtime`): builds native, M26-only-header and
  combined-header helpers from `facade_entrypoint.cc`, requires all seven Rust
  facade imports in selected helpers and none in native, checks the production
  header/local ABI against the SDK, then runs `facade_entrypoint.php`. Header
  variants against one DSO are not separate production feature builds.

The 31 `swoole_stdext` originals run through `corpus/upstream/run.py`
(`phphelpers-full-originals`). Known result: macOS 31 PASS per engine; Linux 30
PASS / 1 FAIL per engine (`mb_ucfirst` missing on PHP 8.2). The stream original
uses `/tmp/test.txt`. Do not rerun the earlier method-alias fixture: it was
stopped by a signal and has no isolated reproduction.

## Benchmark preparation

- `prepare_benchmark.py --source PINNED --work-root DIR --output F`: five modeled
  alias/argument workloads from `benchmark.cc`, run with `--check`.
- `prepare_php_benchmark.py` (loaded PHP arguments plus `--sdk-report`): 16
  `php_benchmark.php` workloads through the producer DSOs with `--check`; requires
  optimized native `CXXFLAGS` and an optimized selected Rust profile.

Neither reads a clock. Measurement (`--measure`) must run without concurrent
workloads; none has run.

## Unit tests

```sh
for t in tests/modules/phphelpers/test_*.py; do python3 -m unittest "$t"; done
```

## Open gates

Loaded runtime for the keyed-merge routing, String/CharPtr release decision and
String dup/edup routing awaits a matching production build. The 48 optional DB
async callers have no runtime qualification (6 SQLite and 11 ODBC compile on
macOS; 31 Oracle/Firebird callers are not compiled). Whole caller/lifetime/fatal/
OOM/DEBUG/ZTS coverage, other architectures, separate production feature builds,
performance and default activation remain open.
