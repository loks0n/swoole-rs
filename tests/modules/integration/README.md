# Rust bridge integration gate

Build the pinned reference and Rust hybrid, then run:

```sh
python3 tests/modules/integration/test_bridge.py
python3 tests/modules/integration/test_bridge.py --hybrid target/hybrid/rust-websocket/modules/swoole.so
```

Requires PHP, C/C++ compilers, `ar`, `make`, and the hybrid's existing libtool
object files. The selected build supplies its own copied static archive and
expected feature bits from its manifest, so compiling another feature combination
does not change this test's inputs. Override with `--archive`/`--feature-bits`;
select extensions with `--reference`/`--hybrid`, and PHP with `--php`.

The tests execute C and C++ consumers, check the real reference/hybrid PHP
markers and PHPinfo, and prove PHP rejects an incompatible bridge ABI. That
negative test relinks existing hybrid objects against a temporary C archive
returning ABI 999. For a WebSocket-enabled build it also proves startup rejects
an ABI-1 archive missing the required feature bit. Temporary fixtures export all
required symbols so the loader reaches the actual module startup check on Linux.
It runs libtool in a temporary directory and loads only the
temporary extension. It neither rebuilds sources nor replaces published modules.
No unsupported or missing artifact is reported as a pass.
`--startup-only` runs only the positive startup and flag checks.

## Other gates

- `php_statistics.py --engine hybrid=SO --engine upstream=SO --build-manifest M
  --archive A --source-ref REF --selected-export export.json --native-export
  export.json --output R` (dev.py phase `phpcoroutines-statistics`). It verifies
  both exports and the selected build's source attestation, then requires that
  `tests/modules/phpcoroutines/statistics.php` gives identical read-only
  Coroutine statistics in the native and selected DSOs.
- `zts.py --checkout DIR --source S --rust-export export.json --output R` needs
  Linux with a ZTS PHP. It builds native and selected ZTS extensions from a
  verified Rust export and checks startup, ZTS, feature bits and the
  `Swoole\Thread\Lock` class. `--locks-threads` also runs
  `tests/modules/locks/threads.py`.
- `zts_originals.py --checkout DIR --source S --zts-report R --output R2` reuses
  the worlds that `zts.py` built. `--profile stdext-originals` (the default)
  runs the complete stdext PHPT originals. `collections` runs the
  phpcollections fixtures and `statistics` runs the read-only statistics
  fixture. Every profile requires both engines to pass and agree.
- `test_bridge_inventory.py` is a plain unittest (no build needed) for the
  selected-export check in `test_bridge.py`.
