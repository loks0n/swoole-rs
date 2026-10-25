# Buffer/String compatibility end state (design)

Design only. When it was written, 35 Buffer/String bodies were still
orchestrated natively:

- Buffer: `empty` (static and instance), BufferChunk constructor/destructor,
  `check_buffer_status`, constructor, `alloc`, `advance`, the compatibility CLOSE
  disposer, and `typed_front`/`consume`/`close`/`sendfile`.
- String: `check_string_status`, `is_system_allocator`, `allocate_string`,
  `edit_string`, `copy`, `grow`, `substr`, `pop`, `print`, `append(int)`,
  `append(bytes)`, `append_random_bytes`, `repeat`, `split`, `ownership`,
  `format_offset`, the byte constructor, `contains`, `empty`, `extend`,
  `extend_align` and `format_impl`.

Each of these bodies needs a native effect at a Zend/C++ ABI boundary: `new[]`/`delete[]`,
exceptions, callbacks, custom allocators, variadic printf. Adding a Rust call in
front of a native branch does not convert the body.

## Pointer and allocator rules

- Keep `new[]`/`delete[]` provenance for legacy public Chunks and real
  sendfile/CLOSE objects. Memory from a Rust `Vec` cannot be passed to native
  `delete[]`.
- String has three allocator families: the mutable standard C functions set in
  `src/core/base.cc`; PHP `emalloc`/`ecalloc`/`erealloc`/`efree`; and Zend-string
  allocate/reallocate/release in `ext-src/php_swoole.cc`. Rust may call only the
  standard C functions, and only after a fresh check that all four are the
  standard ones. The allocator table is mutable, so its identity is not enough. No
  native, Zend or custom allocator, callback, exception or bailout may run through a
  Rust frame.
- Zend buffers are pointers into a real `zend_string`. Consumers recover its header,
  set length/NUL and move it into a zval after `pop`/`release`. That exact pointer
  and header provenance must be kept, and the allocation marked detached before the
  zval takes ownership. Nothing frees it from Rust or the custom allocator afterward.

## Capture/publication order

Each operation needs a per-effect mask of which fields are captured before an
effect and which are re-read after it. Snapshotting everything up front, or
re-reading everything, is wrong. From the pinned source:

- Initial alloc publishes length/capacity/offset before malloc, and pointer and
  allocator after. Reserve publishes only the new pointer and capacity after realloc.
- Grow publishes length before reserve. Custom COPY reads the source payload/length,
  and the final offset, at their original points after allocation.
- Pop captures the old pointer and remaining length before malloc, then reads the
  offset when copying.
- Assignment captures the old allocation before native free, then reads the
  copy/move source after it.
- Random encoding destroys its temporary before publishing the final length.

## Proposed shape

1. A whole compatibility protocol inside the buffer module. Public String fields
   stay authoritative, and Rust owns decisions, capture/publication masks and
   continuation.
2. A separate, initially-off typed String with one inline Rust-owned state cell and
   no duplicated public fields. Its layout needs exact C/Rust/SDK proof first.
3. Migrate whole caller families together: field access, allocation, commit,
   detached-pointer transfer and declared pointer types. Return-type-only C++ ABI
   changes need new function names, because return types are usually not part of
   the mangled name. A field proxy or union view is not a substitute.
4. External code that writes String fields directly, or uses custom callbacks
   expecting the old object, stays on the legacy path.

`zend::String` (`php_swoole_cxx.h`) is a separate Zend wrapper, not
`swoole::String`. The DTLS Buffer is also separate.
