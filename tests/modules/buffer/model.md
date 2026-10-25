# Seeded buffer model gate

```sh
python3 tests/modules/buffer/model.py --sanitize
python3 tests/modules/buffer/model.py --archive /absolute/libswoole_rs_ffi.a --sanitize
```

With `--build-manifest` (default `target/hybrid/rust-buffer-websocket/build-manifest.json`)
the archive, ABI header and facade patches must match the manifest. `--archive`
checks a private archive without an extension build.

Six fixed xorshift seeds (`1`, `7`, `42`, `305419896`, `3735928559`,
`11400714819323198485`) each drive 64 operations at chunk sizes 0, 1, 4 and 16.
Errors name the seed, step, chunk size and allocation-failure ordinal, so a
rerun reproduces the sequence.

An independent C++ deque holds expected bytes, chunk boundaries, consumer offsets
and native tokens. Vector appends flatten to a byte suffix, including empty
descriptors, exact vector boundaries and exact-total no-ops. After every operation
the real C ABI is checked for byte/count accounting, front contents, token identity
and pointer stability; draining checks every remaining entry.

Six more seeded sequences drive the patched C++ facade: partial offsets, mixed
native/data entries, live-data callbacks before pop and FIFO native callback
disposal on pop and teardown.

Two engines run:

- **Published:** the selected build's release archive.
- **Allocation fixture:** the unchanged production Rust source compiled with a
  test-only `GlobalAlloc` (`model_allocator.rs`). A baseline run counts
  allocations, then the whole sequence replays once per allocation ordinal with
  exactly that allocation failing. Failed operations must leave queue contents,
  counters and native ownership unchanged.

Default report: `target/reports/buffer-model.json`. The suite is single-threaded
and bounded; it does not cover sockets, sendfile, fork, fuzzing or large lengths.
