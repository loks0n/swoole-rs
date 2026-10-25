# String direct-field cells (`swr_v1_string_fields_step`)

`SWOOLE_RS_STRING_DIRECT_FIELDS` is off when absent or 0. Enabling it requires Rust
Buffer, arm64 Darwin LP64 and Apple Clang build `21000101`; any other target or
compiler is refused at build time. The class must be standard-layout and
non-polymorphic, with exactly five field types and checked size, alignment,
offsets and signed `off_t`. The allocator field is the real
`const swoole::Allocator *`, imported as a typed opaque token that Rust never
inspects or calls. The C schema in `swoole_rs_string_fields.h` is only a layout
witness and is never used as an lvalue over the C++ object.

`swr_v1_string_fields_step` takes the mutable String address, a separate const
source and a mutable move source. Rust touches only individual raw member cells:
there is no whole-record read/write/copy, no mirror, no retained borrow, no
callback and no allocation.

## Operations

- **Constructors, sized allocation, reserve**: never read uninitialized cells. The
  default allocator is resolved before alignment/reset. Length, capacity and offset
  are set before malloc, then the pointer and allocator token are published. A
  successful realloc publishes only pointer and capacity. The byte constructor
  copies at offset 0, writes the NUL, then sets the length.
- **APPEND / WRITE / integer / REPEAT / COPY / terminate / POP**: reuse the regular
  Rust compatibility logic directly. Rust handles reserve and initial-allocation
  subphases itself. REPEAT keeps the per-append allocation cadence.
- **Assignment, dispose/free, clear/release, grow, reduce**: self-assignment is
  checked before any effect. Native free runs after Rust returns, without clearing
  ownership fields first. Copy and move re-read their sources after the effect.
  Move keeps ordered per-field reads/stores and the moved-from allocator token.

Native runs only the returned default-allocator/malloc/realloc/free effect and
converts terminal statuses into the existing exceptions. Queries, substr/print,
random, formatting and split are not yet converted to direct fields.

Test:

```
python3 tests/modules/buffer/string/compatibility.py --source PINNED_SOURCE \
  --archive EXACT_SELECTED_ARCHIVE --sanitize --direct-fields --output UNIQUE_JSON
```
