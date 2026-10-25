# Packet framing and MIME (M18)

The overlay replaces `src/protocol/base.cc` and `src/protocol/mime_type.cc`. The public
Protocol, PacketLength, Socket, String and MIME declarations are unchanged.
`swoole_rs_framing.h` declares ten exports. Feature bit 4096 is the optional
framing feature; the module is opt-in.

## Packet framing

- Rust makes the receive/length/EOF dispatch decisions in a stack-local scalar
  state machine. Each call borrows only the current snapshot's data and delimiter
  bytes and keeps no pointer.
- Rust returns before native receives, errors, SSL calls, buffer
  allocate/resize/reduce, length callbacks or package callbacks run. Snapshots are
  refreshed after each native action. Exceptions, including String allocation
  failure, unwind only through native frames.
- Kept from upstream: callback removal/failure order, recursive entry, captured
  dynamic header size, partial packets, sticky EOF retry and always growing to the
  next page.
- `swr_v1_framing_unpack` handles all sixteen formats, native 32-bit int and
  64-bit size_t, unaligned loads, signed values and endianness. The default
  length helper keeps the original `header_len` assignment, including the
  dynamic-size quirk. Invalid-format diagnostics run natively after Rust returns.
- Borrowed pointers must cover the given length; null is accepted for length 0.
  Output pointers must be live, aligned and disjoint from the input and from each
  other. State and snapshot pointers must not alias mutable state.

## MIME

- The 362 catalog entries and the fallback bytes are immutable in Rust.
- One native `unordered_map` is the only mutable store, because the public API
  returns C++ container and value references. list/add/set/del/get/exists remain
  native shims; Rust has no mutable registry or duplicate index. Construction uses
  the original insertion order. Rehash keeps value identity, and erase keeps
  native iterator invalidation.
- Lookup is case-sensitive on mutation, uses the last dot, and handles no-dot,
  trailing-dot and embedded-NUL input. Case mapping uses host libc. Suffix input
  and output must be disjoint.
- `swr_v1_framing_mime_suffix_offset` returns the offset just past the last dot
  (0 if there is no dot) or `SIZE_MAX` for an invalid extent. `get_suffix`
  allocates only the suffix and passes it to `swr_v1_framing_mime_suffix` for case
  folding. No Rust borrow is held across the native allocation.

## Deliberate differences from upstream

These differ only where upstream has undefined or unsafe behavior:

- A format wider than the reported packet bytes is rejected instead of read past
  the end. A declared dynamic size smaller than its format can trigger this.
- An overflowing signed total length is rejected (signed overflow is UB natively).
- A receive request larger than the buffer's remaining allocation is rejected.
- For C `tolower`, signed-char 0xff keeps EOF behavior; other negative signed-char
  values are converted to unsigned (the original call is UB for them).

Tests: `tests/modules/framing/`.
