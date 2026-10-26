# String storage boundary

`crates/buffer/src/string.rs` and `crates/buffer/src/string/` implement the
`swoole::String` allocation, growth, append/write/repeat, compaction, pop, query,
split, format and random-append policies. Declarations are in
`swoole_rs_string.h` (included by `migration/patches/buffer/0003-string-storage.patch`).
The public `swoole::String` layout is unchanged: callers still access `str`,
`length`, `size`, `offset` and `allocator`. Native code passes independent
`swr_v1_string_state` POD snapshots. No C++ layout, Rust reference, Zend value or
exception crosses the boundary, and there is no registry or side map.

## General rules

- Rust never calls an allocator, Zend function or native callback, except the
  direct-libc `swr_v1_string_edit_system` described below. Native runs
  malloc/realloc/free (including `emalloc`/`erealloc` and Zend string allocators,
  which may bail out) after Rust returns.
- A state describes uniquely owned storage with matching allocator provenance.
  PODs and outputs are valid, aligned and mutually disjoint. Input bytes are
  initialized and either disjoint or entirely inside the allocation. Nothing may
  mutate the object between prepare and apply (no reentry or concurrency).
- Length ≤ capacity ≤ `isize::MAX`. Growth keeps the native unsigned-long alignment
  and configured page size.
- Status: 0 = ok, -1 = invalid input/state/plan, -2 = overflow, -3 = native
  malloc/realloc returned null (translated outside Rust). A failed prepare zeroes
  its output. A failed apply zeroes its detached output. Bytes change only after a
  successful allocation, so the facade keeps the old state on failure or bailout.
- Interior input is carried as an offset and rebased onto the new pointer after
  realloc. No Rust borrow survives an FFI call.

## Edit plan/apply

`swr_v1_string_prepare` validates a state and edit, then returns the resulting
metadata, requested capacity, allocator action (0 = none, 1 = malloc, 2 = realloc)
and any interior source offset. Native allocates, then `swr_v1_string_apply` copies
bytes and publishes the state. Drop and pop detach the old owner, and native frees
or transfers it afterward.

Edit operations (`SWR_STRING_*`): RESERVE, APPEND, WRITE, REPEAT, REDUCE, POP,
DROP, TERMINATE (7), COPY (8), APPEND_I32 (9).

- Append keeps the offset. Write keeps the offset and extends to its last byte.
  Gap bytes are unspecified, as in upstream.
- Reduce(0) does nothing; other reduce values shift the suffix and clear the offset.
  Pop copies the suffix into a separate new allocation and transfers the old owner.
- Zero-size resizes use malloc/free so a null result never loses ownership.
  Shrinking below the live length is rejected.
- TERMINATE grows only when length == capacity, to exactly aligned length+1, and
  writes only the NUL. Count 0 = owned storage. Count 1 = a borrowed writable span:
  spare capacity is filled without allocating, and needing growth is rejected.
- COPY: data/length are the source bytes, count is the source capacity, offset is
  the source offset, and page is a boolean "same object" fact. It needs an empty
  destination and plans one malloc of the exact aligned source capacity. The fused
  path is used only when all four allocator functions are standard libc. Custom
  and Zend allocators use the alloc-then-append pipeline, so the source is read
  fresh after allocation.
- APPEND_I32: offset carries the signed value, formatted with `itoa`.

Fast paths:

- `swr_v1_string_edit_in_place` returns 0 if the edit completed without
  allocating, or 1 with the plan unchanged if allocation is needed.
- `swr_v1_string_append_in_place` takes data, a length pointer and capacity, and
  copies only if the bytes fit (else returns 1).
- `swr_v1_string_append_i32` returns the same allocation-needed status, and the
  caller then uses APPEND_I32.
- `swr_v1_string_format_i32` writes 1..=11 decimal digits plus a NUL into a 12-byte
  buffer and returns the count without the NUL. A null output returns 0.

Deliberate extensions: internal-alias appends and repeats stay valid across
realloc; overlapping writes behave like `memmove`; invalid or overflowing requests
fail before mutation; direct-v1 REPEAT reserves once and doubles the copied prefix.

## Direct libc edit

`swr_v1_string_edit_system` calls C malloc/realloc itself. The caller must confirm
that all four allocator functions are the standard
malloc/calloc/realloc/free. Allocator table identity is not enough, because the
table is mutable. A null allocation returns -3 with state unchanged. Public String
callers use `swr_v1_string_edit_object` instead.

## Queries and plans

- `swr_v1_string_match`: CONTAINS, STARTS_WITH, ENDS_WITH, EQUALS. Empty CONTAINS
  is invalid. The native contains wrapper keeps the pinned uint32 length truncation.
- `swr_v1_string_range`: substring bounds with overflow checks (an empty range at the
  exact end is allowed).
- `swr_v1_string_split_next` does one delimiter step and returns before the handler
  runs. `swr_v1_string_split_plan` adds a scalar cursor (initial prefix, previous
  advance, handler-pending bit). It returns -1 for a false handler, then the
  advance/prefix reset and the next scan. The returned offset must be published
  before checking an error. Native reads fresh bytes and metadata after each
  callback, so appends, reallocation, mutation and offset changes in the callback
  are observed. A thrown handler never re-enters Rust.
- `swr_v1_string_capacity`, `swr_v1_string_grow`, `swr_v1_string_format_plan`,
  `swr_v1_string_random_plan` are pure, checked calculations. Legacy grow publishes
  the length before the native reserve.

Corrections: a fragment shorter than the delimiter keeps offset 0 instead of going
negative, and growing from zero capacity terminates instead of looping.

## Metadata transitions and ownership

- `swr_v1_string_transition`: TAKE (1) transfers the owner and metadata and resets
  the source to null/zero. It never dereferences storage. Invalid input returns -1
  and zeroes the output. Move and release use it. Release returns the pointer without
  freeing it.
- `swr_v1_string_ownership_plan` (DISPOSE/COPY/MOVE): self-assignment has no
  effects. Otherwise an allocator-owned non-null pointer is freed natively
  (OWNER_FREE) before DO_COPY/DO_MOVE. Borrowed or null pointers are not freed.
  Fields stay visible until the native free, as in upstream.
- `swr_v1_string_allocation_plan` (INITIAL/RESERVE): initial allocation never reads
  uninitialized fields. Native publishes length = 0, aligned capacity and
  offset = 0 before malloc, then the pointer and allocator after. A successful
  realloc changes only pointer and capacity.

## Multi-phase operations

These return a phase to native, which performs the effect and passes fresh
observations back in:

- `swr_v1_string_format_step`: phase 0 = sizing printf result (done, reserve or
  render), 1 = after reserve, 2 = render result. Empty sizing returns early without
  writing or reserving. Native keeps the variadic arguments and libc printf.
- `swr_v1_string_random_step`: RESERVE, ENTROPY, OWNER, ENCODE, COPY, PUBLISH,
  FALSE, TRUE, FREE. A short read returns false before any encoder work. The length
  is published after the encoder's temporary is released.

## Whole public operations

`swr_v1_string_edit_object` runs public APPEND (bytes and String), WRITE,
APPEND_I32, REPEAT, COPY, POP and termination in one call. Native passes the
String's fields and allocator; Rust calls the allocator itself and edits the
fields, which native copies back even on error. First allocations use `initial`:
the source's allocator for COPY, else the standard one. Fields are published in
the original order, so a failed allocation leaves what the original left.
Multi-byte REPEAT appends once per element (original allocation cadence). POP
returns the old storage, or null without changes when malloc fails.

## Performance

Measured on macOS ARM64 (see `tests/modules/buffer/string/algorithms.md`):
throughput vs upstream is 1.04x warm append, 0.77x cold append, 1.16x repeat,
0.91x write/reduce, 0.95x queries, 1.01x framed split, 0.99x missing delimiter.
The cold, write and query regressions block default activation.

## Validation

```sh
cargo test -p swoole-rs-buffer --offline
cargo clippy -p swoole-rs-buffer --all-targets --offline -- -D warnings
cargo rustc -p swoole-rs-buffer --release --offline --locked --crate-type staticlib
python3 tests/modules/buffer/string/gate.py --original-only \
  --source target/upstream/src \
  --archive target/release/libswoole_rs_buffer.a --sanitize \
  --output target/string/gate-original.json
```

`gate.py` without a profile flag writes `STOPPED_NOT_RUN` and does nothing.
`--original-only` runs all 23 unchanged pinned `core-tests/src/core/string.cpp`
tests against both engines. Focused positive profiles: `--transition-only`,
`--copy-only`, `--split-only`, `--integer-only`, `--ownership-only`,
`--allocation-only`, `--format-only`, `--random-only`. The gate needs the pinned
native core/base, os/base and base64 sources and `pkg-config openssl`. ASan/UBSan
covers the C++ side only. `tests/modules/buffer/string/test_compatibility.py` checks
`swr_v1_string_edit_object`; `production.py --consumer compatibility` loads it into a PHP
build. See `tests/modules/buffer/string/profiles.md`.
