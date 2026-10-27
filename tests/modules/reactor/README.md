# Reactor gates

`python3 tools/dev.py` registers most of these as phases when the `reactor`
module is selected. Scripts can also be run directly from the repo root.

## Source-body facades

Most gates take the pinned upstream source and a Rust FFI archive:

    python3 tests/modules/reactor/NAME.py --source target/upstream/src \
        --archive PATH/libswoole_rs_ffi.a --sanitize --report OUT.json

`NAME` is one of `output`, `wait`, `callbacks`, `callback_queues`,
`initialize`, `builtins`, `backend_storage`, `flush`, `poll_snapshot`,
`write_gate`, `stream_gate` and `iov_owned`. Each extracts the original and patched function
bodies from upstream after applying `migration/patches/reactor/` (patch
checksums must match the manifest), compiles them against native facades and the
archive, and checks that both variants behave the same. `output.py` also takes
`--iov-progress` or `--forwarding`.

Gates that need no upstream source:

- `compile_gate.py --source S --report R`: original and patched backend translation units compile as C++14.
- `buffer_typed_compile.py --source S --master-patch P --report R`: typed Buffer compositions compile.
- `declarations.py --archive A --report R`: every `swr_v1_reactor_*`/`swr_v1_stream_*` declaration in the header is defined in the archive.
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
`--builtins`, `--socket-output`, `--blocking`. Extra identity checks: `--require-owned-iov` (with
`--blocking`) and `--require-owned-defer` (with `--builtins`) check the Rust-owned storage
imports and origins against the Native control; `--require-output-workflow`
(with `--socket-output`) and `--require-typed-buffer` refuse a selected build
whose source predates the required Rust code.

Known failure: the original broad production profile failed on Native kqueue (a
missing WRITE filter deletion warned, and its assertions assumed poll ordering
and ONCE across separate kqueue records). The supported profile covers
single-filter kqueue records only.

## Sanitizer

`rust_asan.py --source S --target EMPTY_DIR --report R --PROFILE-only` builds
the reactor crate with `-Zsanitizer=address`, runs its filtered unit tests and
the matching facade gates against the instrumented archive. A profile flag is
required. Cargo intermediates go in a keyed cache beside `--target` (or under
`--dependency-target-root`).

## Unit tests

    cd tests/modules/reactor && python3 -m unittest test_*.py

`test_staging.py` checks that overlays apply identically inside an ignored Git
parent and an independent directory (skipped without `target/upstream/src`).
`test_buffer_typed_identity.py` and `test_sockets_source.py` read historical
commits with `git show` and fail in checkouts that lack them.
