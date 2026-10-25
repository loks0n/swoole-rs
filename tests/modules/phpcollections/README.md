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

`make_patches.py --source PINNED` regenerates both overlays (inserting the
`table_facade.inc` template); selected sources require
`--enable-swoole-rs-phpcollections`.

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

`handlers.py` takes the runtime arguments plus `--source PINNED`, runs the runtime
prerequisite, then runs `channel_construct_check`, `unset_deny` and
`unset_property_01` with PHP's official runner (`phpcollections-global-handlers`).

`originals.py` takes the same arguments plus `--redis-extension FILE` and runs all
63 Table/Channel originals against a private Redis (`phpcollections-prerequisites`).
Linux defaults to managed `redis-server`/`redis-cli` (or `--redis-server`,
`--redis-cli`); load `--php-extension igbinary` before Redis. macOS can use
`--redis-image sha256:IMMUTABLE_ID`. Port 6379 is refused; teardown is verified.
`--case PATH` runs a supplemental subset.

Known results: macOS 53 PASS / 10 SKIP; Linux 52 PASS / 1 FAIL / 10 SKIP per
engine. Linux `force_unlock` misses its expected native warning. The ten Channel
skips are eight `select`, one hanging and one offline case. The mixed
`serialize_deny` case is not run under M27.

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
