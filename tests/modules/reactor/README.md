# Reactor gates

`python3 tools/dev.py` registers most of these as phases when the `reactor`
module is selected. Scripts can also be run directly from the repo root.

## Source-body facades

Most gates take the pinned upstream source and a Rust FFI archive:

    python3 tests/modules/reactor/NAME.py --source target/upstream/src \
        --archive PATH/libswoole_rs_ffi.a --sanitize --report OUT.json

`NAME` is one of `registration`, `write_positive` (`--workflow` for the write
workflow), `write_arguments`, `output`, `wait`, `callbacks`, `callback_queues`,
`initialize`, `handlers`, `builtins` (`--defer-owned`), `backend_storage`,
`flush`, `poll_snapshot`, `ordered_gate`, `filters_gate`, `write_gate`,
`stream_gate` and `iov_owned`. Each extracts the original and patched function
bodies from upstream after applying `migration/patches/reactor/` (patch
checksums must match the manifest), compiles them against native facades and the
archive, and checks that both variants behave the same. `output.py` also takes
one of `--blocking`, `--iov-progress`, `--ordinary-io`, `--socket-policy`,
`--fd-options`, `--socket-options`, `--forwarding`, `--datagram` or `--connect`.

Gates that need no upstream source:

- `batch.py --archive A --report R [--sanitize]`: kernel-array decode and POD layout.
- `socket_iterators.py --archive A --report R [--sanitize]`: registry iterators.
- `sockets.py --source S --archive A --report R [--sanitize] [--order-model --standard c++14]`: socket registry source order.
- `sockets_policy.py --report R`: compile/refusal contract of the socket-registry configuration macros.
- `compile_gate.py --source S --report R [--sockets-owned]`: original and patched backend translation units compile as C++14.
- `buffer_typed_compile.py --source S --master-patch P --report R`: typed Buffer compositions compile.
- `declarations.py --archive A --report R`: every `swr_v1_reactor_*`/`swr_v1_stream_*` declaration in the header is defined in the archive.
- `callback_internal.py --report R`: compares current and control Rust callback metadata operations.
- `sockets_gnu_source.py --candidate-dir D --report R`: compares the Rust socket store with GNU libstdc++ hashtable bodies (inputs pinned by checksum in `gnu_source_body.py`).


## Production consumer

`production_supported.py` loads the real Native and selected `swoole.so` builds,
compiles a small PHP addon (`production_supported.cc`) against each build's
reconstructed headers, and runs the matching `production_*.php` fixture under
both engines:

    python3 tests/modules/reactor/production_supported.py --source target/upstream/src \
        --source-ref HEAD --engine hybrid=SELECTED/swoole.so --engine upstream=NATIVE/swoole.so \
        --build-manifest SELECTED/build-manifest.json --archive SELECTED/libswoole_rs_ffi.a \
        --selected-export SELECTED/export.json --native-export NATIVE/export.json \
        --require-batch --output OUT.json

Profiles: default (readiness over AF_UNIX socketpairs), `--callbacks`,
`--handlers`, `--builtins`, `--socket-output`, `--blocking`, `--ordinary-io`,
`--datagram`. Opt-in ownership checks: `--require-owned-iov` (with
`--blocking`), `--require-owned-defer` (with `--builtins`),
`--require-owned-sockets` (default profile), `--require-output-workflow` (with
`--socket-output`) and `--require-typed-buffer`. Each refuses a selected build
whose source predates the required Rust code.

Known failure: the original broad production profile failed on Native kqueue (a
missing WRITE filter deletion warned, and its assertions assumed poll ordering
and ONCE across separate kqueue records). The supported profile covers
single-filter kqueue records only.

## Sanitizer and benchmarks

`rust_asan.py --source S --target EMPTY_DIR --report R --PROFILE-only` builds
the reactor crate with `-Zsanitizer=address`, runs its filtered unit tests and
the matching facade gates against the instrumented archive. A profile flag is
required. Cargo intermediates go in a keyed cache beside `--target` (or under
`--dependency-target-root`).

`performance.py --prepared P --backend poll|kqueue|epoll --output R` validates
prepared upstream/reactor consumers; `--measure` runs the timing loop and should
be used without concurrent workloads.

## Unit tests

    cd tests/modules/reactor && python3 -m unittest test_*.py

`test_staging.py` checks that overlays apply identically inside an ignored Git
parent and an independent directory (skipped without `target/upstream/src`).
`test_buffer_typed_identity.py` and `test_sockets_source.py` read historical
commits with `git show` and fail in checkouts that lack them.
