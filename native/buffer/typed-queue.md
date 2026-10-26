# Typed Buffer queue (`swr_v1_buffer_typed_*`)

`SWOOLE_RS_BUFFER_TYPED` is on whenever both the Rust Buffer and the Rust reactor are
built (`--module buffer --module reactor`); there is no separate switch. It reuses the single Rust `VecDeque` and
byte ownership, adding a Rust front cursor and generation plus ordered sendfile
token and CLOSE entries. Exports: `create`, `push`, `front`, `consume` (cursor) and
`pop` (detach). There is no native descriptor queue or DATA offset mirror.

- Queued bytes stay counted until the DATA entry is detached. A partial send moves
  only the Rust cursor. Generation and offset are checked before publishing.
- The Buffer constructor, typed enqueue/front/consume and the existing pop/drain
  callers use these operations. Native callback and token disposal run after Rust
  returns. Rust stores native function addresses but never calls them.
- Legacy create/front/pop/advance/push behave as before on legacy handles. The
  mutable legacy front, `alloc` of DATA and legacy sendfile are not available on
  typed handles; the legacy front API rejects them.
- Ordinary CLOSE markers and sendfile ownership allocate nothing. The optional
  native close repair still calls `alloc(TYPE_CLOSE)`. It gets a real native
  `BufferChunk`, which is pushed into the same Rust queue with a native disposer.

## Layout

- When enabled, the C++ Buffer holds only the Rust pointer (8 B; 56 B when absent or
  0). The public `Chunk` is unchanged (40 B).
- The Rust owner is one enum `Mode` value: either the borrowed legacy facade
  identity or the typed cursor. It is 64 B on macOS arm64 (Entry 32 B, Front 40 B,
  Detached 16 B), compared with 48 B before the typed queue, for legacy handles too.
  C/Rust front and detach layouts are verified on macOS only.
- Typed and legacy creation share one fallible `Box` and the same raw
  admission/publication adapter. Teardown pairs `Box::into_raw` with
  `Box::from_raw`.

Tests: `tests/modules/buffer/typed.py`, `typed_layout.py`.
