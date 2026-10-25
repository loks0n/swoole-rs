# Hybrid build

The hybrid build links a Rust static library into upstream Swoole's PHP
extension through [ABI v1](abi-v1.md). With no modules selected, the Rust side
supplies only the version/feature queries and all behavior is upstream. One
Swoole extension is loaded per PHP process.

The reference is Swoole v6.2.2, commit
`8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e`, at `target/upstream/src/`. The
builder refuses a different commit or tracked modifications there, and applies
checksum-verified patches from `migration/patches/<module>/` to a separate Git
clone. Do not edit the reference to develop a patch.

## Editing patches

Each module's patches are a branch of the pinned upstream, one commit per patch
file named after it:

```sh
python3 tools/patches.py checkout phphelpers   # target/patches/phphelpers, branch patches/phphelpers
# edit, then amend or fixup the commit for that patch (git rebase -i 8e8c499)
python3 tools/patches.py export phphelpers     # rewrites the patch files and manifest.json
rm -rf target/patches/phphelpers
```

Upstream changes then surface as ordinary rebase conflicts. Export writes
`git diff` output and drops patch files that no longer have a commit; add a
commit to add a patch. New destinations must be in the module's
`upstream_patch_targets` in `migration/modules.json`.

## Build variants

Needs the PHP toolchain from the [corpus instructions](../corpus/README.md) plus
Rust/Cargo. Run from the repository root.

```sh
python3 tools/check_migration.py
python3 tools/build_upstream.py

python3 tools/build_hybrid.py                      # ABI bridge only
python3 tools/build_hybrid.py --backend upstream   # patched build, Rust bridge disabled
python3 tools/build_hybrid.py --module websocket
python3 tools/build_hybrid.py --module buffer --module websocket
```

`--backend rust` is the default; `--module` requires it. Module names and
feature values are listed in [migration modules](migration-modules.md).
Upstream keeps PHP objects, socket/reactor ownership, protocol dispatch and
native callbacks unless a selected module replaces them.

Shared options (also on `build_upstream.py`): `--jobs N`, `--php-config PATH`,
`--phpize PATH`, `--openssl-dir PREFIX`, `--stdext`, `--php-sockets`,
`--ccache PATH` / `--no-ccache` (ccache is auto-detected and uses its own
settings). The runners' `--php` must match the build
toolchain. Neither builder installs the extension or edits php.ini.

Stable paths point to the latest build of each variant:

| Variant | PHP extension |
| --- | --- |
| Reference | `target/upstream/src/modules/swoole.so` |
| ABI bridge | `target/hybrid/rust/modules/swoole.so` |
| Upstream fallback | `target/hybrid/upstream/modules/swoole.so` |
| Modules | `target/hybrid/rust-<module>[-<module>…]/modules/swoole.so` |

Builds live in `target/hybrid/builds/<input-sha256>/` with `src`, `modules`,
`rust-prefix/` (archive and headers), `state.json`, `build-manifest.json` and
`build.log`. Variant directories symlink into them, so a rebuild can move a
stable path; record the resolved path and SHA-256 that runners print. The
clones share Git objects with the reference checkout, so keep it in place.

The input hash covers backend/modules, pinned commit, ordered patch hashes and
destinations, builder hashes, configure arguments and pkg-config CPPFLAGS,
exported headers, the Rust archive, toolchain versions and compiler environment.
A cached build is reused only if its source diff, pin and artifact checksum
still match; otherwise the builder refuses and leaves the directory for
inspection. Patch hunk offsets must be exact; a patch that only applies with
an offset is rejected. Builds are traceable but not byte-identical: upstream
embeds `__DATE__`/`__TIME__`.

`--export /absolute/new-directory` copies the DSO, Rust archive, config,
manifest, Makefile and build log of an immutable build into a new directory
with an `export.json` receipt. It never replaces an existing export and is
rejected with `--dev`.

`--dev` uses an incremental tree; see [development](development.md).

## Optional build switches

All default off and get their own alias suffix and manifest input.

| Switch | Requires | Effect |
| --- | --- | --- |
| `--fix-halfclose` | — | M15 native patches: drain queued output before close. No Rust feature bit. Changes behavior relative to the reference; does not make general TCP half-close work. |
| `--http-rewrite-store` | `--module http` | Rust-owned HTTP rewrite-rule storage (`--enable-swoole-rs-http-rewrite-store`). |
| `--http-static-config` | `--module http` | Rust-owned `StaticConfig` and static consumers. Changes the public Server configuration fields and layout; rebuild SDK consumers. |
| `--http-legacy-directory-store` | `--module http` | Rust-owned legacy StaticHandler directory catalog. Old compiled `std::set` callers are not compatible; rebuild consumers. |
| `--buffer-typed` | `--module buffer --module reactor` | Rust Buffer cursor with converted Socket/reactor/server callers. Legacy mutable DATA front/allocation is refused in this mode, so unconverted consumers break. |
| `--string-direct-fields` | `--module buffer` | Rust operates directly on the five `String` member fields. Only arm64 Darwin with the Apple compiler is accepted. |
| `--reactor-{iov,defer,sockets}-owned` | `--module reactor` | Rust-owned iov/defer/sockets storage. |

## Timer module

`--module timer` (feature value 4) is opt-in only. `tests/modules/timer/test_fork.py`
checks forking from an active timer callback, which aborted the child in the
first adapter.

## Running the corpus and PHPTs against builds

```sh
python3 corpus/run.py \
  --engine hybrid=target/hybrid/rust/modules/swoole.so \
  --engine upstream=target/upstream/src/modules/swoole.so \
  --require-all --output target/reports/corpus-hybrid.json

python3 corpus/upstream/run.py \
  --engine hybrid=target/hybrid/rust/modules/swoole.so \
  --engine upstream=target/upstream/src/modules/swoole.so \
  --require-all --output target/reports/phpt-hybrid.json
```

Runners use `php -n`. Where PHP modules are dynamic, pass
`--php-extension pdo --php-extension pdo_sqlite --php-extension curl
--php-extension sockets` (and `tokenizer` for the Hyperf project) consistently
to every command. Do not pass these for modules built into PHP (Homebrew):
duplicate-module warnings break PHPT output. PHPTs run through PHP's official
runner; never use upstream's custom runner or `tests/start.sh`.

Benchmarks, after builds and tests have finished:

```sh
python3 benchmarks/run.py \
  --engine hybrid=target/hybrid/rust/modules/swoole.so \
  --engine upstream=target/upstream/src/modules/swoole.so \
  --requests 5000 --concurrency 1 16 --warmup 20 --repeat 3 \
  --output target/reports/benchmarks-hybrid.json
```

These localhost measurements can be client-limited and do not measure codec
throughput. Module-specific gates are in [validation](validation-suite.md).
