# swoole-rs

A gradual C/C++ to Rust migration of the [Swoole](https://github.com/swoole/swoole-src)
PHP extension. Upstream Swoole v6.2.2 (pinned at `8e8c4991`) keeps its PHP runtime;
bounded subsystems are replaced with Rust linked into the upstream extension through
a C ABI. Each Rust module is opt-in, and omitting it selects the pinned upstream code.
Full coverage, parity and performance remain in progress. See the
[migration approach](docs/migration.md) and [hybrid variants and evidence](docs/hybrid-build.md).

## Build

Requires Rust/Cargo, PHP CLI with matching development headers (`php-config`), and
the upstream build toolchain described in the [corpus instructions](corpus/README.md).

```sh
python3 tools/build_upstream.py
python3 tools/build_hybrid.py --module buffer --module websocket
php -n -d extension="$PWD/target/hybrid/rust-buffer-websocket/modules/swoole.so" -r 'echo SWOOLE_VERSION, "\n";'
```

Do not load the hybrid alongside another Swoole extension: both register the same classes.

## Verify

For edit/candidate loops, incremental hybrid builds and the reusable Linux toolchain,
see [local development](docs/development.md).

```sh
git config core.hooksPath .githooks   # pre-commit: fmt, clippy, manifest, tooling tests (~30s)
python3 tools/dev.py integrate --module buffer --module websocket
```

CI has two tiers. [PR](.github/workflows/pr.yml) runs Rust tests, tooling tests and the
application corpus against a cached hybrid build. [Merge](.github/workflows/merge.yml)
runs every gate and original PHPT for all modules on `main`.

## Modules, corpus and benchmarks

The [migration work packages](docs/migration-modules.md) and
[module manifest](migration/modules.json) define the modules, dependency waves,
exclusive paths, ABI ownership and acceptance gates for concurrent agents. Run
`python3 tools/check_migration.py` before dispatching work.

The [project corpus](corpus/README.md) runs application projects against any engine,
and the [original upstream PHPT selection](corpus/upstream/README.md) runs pinned
Swoole tests with their original assertions. Missing APIs are reported as
unsupported; behavioral failures fail the run. The [benchmark harness](benchmarks/README.md)
compares optimized hybrid and upstream builds. The [validation layers](docs/validation-suite.md)
add allocation-failure models, lifecycle scenarios, an Autobahn RFC profile and an
unchanged pinned Hyperf app.
