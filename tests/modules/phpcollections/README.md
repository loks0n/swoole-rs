# PHP collection facades (M27)

M27 covers the `Swoole\Table` and coroutine `Channel` PHP facades. Rust takes
copied metadata and returns before any native effect. Zend, storage, row/iterator
identity, locks and scheduler custody stay native; no retained Rust frame spans an
effect. See [remaining-native.md](remaining-native.md) and
[body-map.md](body-map.md) for every original function and its native remainder.

The header declares 13 exports. PHP Table uses the M12 TableV2 composition API and
its Rust column store ([table-columns-contract.md](../../../native/phpcollections/table-columns-contract.md));
the legacy public Table ABI is untouched. `value_plan` chooses complete per-value
read/materialize and write/convert/store/release sequences for shared native
dispatchers ([value-pipeline.md](../../../native/phpcollections/value-pipeline.md)).
Channel uses packed action plans, low byte first: phase 0 ends at native
push/pop, phase 1 uses the fresh result. `clear_cell`, `channel_next` and
`write_action` have no selected-facade callers.

Edit both overlays in `migration/patches/phpcollections/` with `tools/patches.py`
(see [hybrid build](../../../docs/hybrid-build.md#editing-patches)); selected sources
require `--enable-swoole-rs-phpcollections`.

## Body and policy gate (`gate.py`)

```sh
python3 tests/modules/phpcollections/gate.py --source /absolute/pinned/source \
  --library-kind cdylib --sanitizers --output target/policy.json
```

Extracts the pinned and selected capacity/count, push/pop, incr/decr/read and set
bodies, compiles them into `gate.cc`, `effects.cc`, `arithmetic.cc` and
`write.cc` with scripted native effect doubles, and compares native and selected
traces. `--archive FILE` uses an existing combined archive instead of building
the crate. `--sanitizers` applies ASan/UBSan to the C++ witness frames only.
Registered in `tools/dev.py` as `phpcollections-policy`.

## SDK syntax check (`sdk.py`)

`sdk.py --source PINNED --sdk-export FILE --output FILE` copies an exported
`config.h` and a clean pinned-header mirror plus the M12 headers, then
syntax-checks native and selected full translation units and expects the selected
units to refuse compilation without the feature define. Only the mirror's M27
define is removed so per-command `-D`/`-U` selects the variant.

## Loaded PHP runtime (`php_runtime.py`)

```sh
python3 tests/modules/phpcollections/php_runtime.py \
  --engine native=/absolute/reference.so --engine selected=/absolute/swoole.so \
  --build-manifest /absolute/build-manifest.json --archive /absolute/ffi.a \
  --source-ref EXACT_SOURCE_COMMIT --output target/runtime.json
```

Copies the DSOs, requires M27 bit 33554432 on exactly one engine, attests the
selected build, then runs `php_collections.php` on both. The `complete` profile
requires exactly 324 checks and identical summaries: binary/null/partial writes,
defined arithmetic, object/resource custody, COW isolation, suspended FIFO
transfer, aliases/Countable/Iterator, constructor refusal, serialization denial,
and column schemas of 1/3/17/65 columns with duplicates. `--profile column-bytes`
runs the separate 16-check `php_column_bytes.php` (NUL/high-byte column names).
Optional PHP dependencies use repeated `--php-extension NAME`. Registered as
`phpcollections-runtime` and `phpcollections-column-bytes`.

## Originals

The PHPT gate (merge tier `phpt-*` jobs) runs every pinned Table, Channel and
`swoole_global` original on upstream and on the all-modules hybrid.

## Benchmark preparation (`prepare_benchmark.py`)

Takes the runtime pair arguments plus `--native-build-manifest FILE`. Optional
paired `--selected-export FILE` / `--native-export FILE` recompute the observed
compiler commands and reject unoptimized builds; `--compilation-correction FILE`
must match exactly one export. It runs seven `benchmark.php` workloads with
`--check` and `hrtime`/`microtime` disabled (new/existing writes, full/field
reads, arithmetic, buffered transfer, handoff), makes the prepared files
read-only and reports remaining eligibility blockers. No measurement mode has run.

## Unit tests

```sh
for t in tests/modules/phpcollections/test_*.py; do python3 -m unittest "$t"; done
```

## Open gates

Fresh loaded production, originals, lifetime and performance runs for the current
TableV2/`value_plan` source; the 324/16-check runtime results so far come from the
earlier vector-backed production build.

## Gate audit (#490)

Kept (3):

- `phpcollections-policy`: native-versus-selected traces of the extracted
  capacity, push/pop, arithmetic and set bodies, against scripted effect doubles.
- `phpcollections-runtime` and `phpcollections-column-bytes`: 324 and 16 loaded-PHP
  checks whose summaries must match upstream exactly. They cover COW isolation,
  object and resource custody, suspended FIFO transfer and binary column names,
  which the PHPTs only pass or fail.

Deleted (2), each a duplicate:

- `phpcollections-global-handlers` reran `phpcollections-runtime`, then three
  `swoole_global` PHPTs that the PHPT gate already runs on both engines.
- `phpcollections-prerequisites` reran the 63 Table/Channel PHPTs that the PHPT
  gate already runs, with Redis services. It ran only under `--redis-extension`,
  which no CI lane passed, so that option and `--redis-image` are gone too.

