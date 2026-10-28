# Rust bridge ABI v1

Rust is statically linked into the existing Swoole PHP extension. No second
extension, scheduler, worker pool or reactor is introduced.

## Base contract (`native/include/swoole_rs.h`)

- `uint32_t swr_v1_abi_version(void)` returns 1.
- `uint64_t swr_v1_feature_bits(void)` returns the mask of compiled modules
  (values in [migration modules](migration-modules.md)). Zero means only
  the bridge is present.

Both are allocation-free, safe on any thread and after fork, and cannot panic
or throw. Module startup rejects an incompatible ABI version or a missing
required feature bit. Hybrid builds also expose PHP constants and a phpinfo
row identifying the bridge.

## Rules for all module contracts

- No C++ layouts, Zend values, Rust references, exceptions or panics cross the
  seam.
- Buffers are released by the side that allocated them. Borrowed pointers are
  valid only for the call. Writable ranges must not alias each other or Rust
  state unless a contract says otherwise.
- Errors are fixed-width integer codes. Lengths must fit the target's
  pointer-size limits (`isize::MAX` for slices).
- An owned handle needs an explicit release function, thread affinity, fork
  behavior and cancellation rules.
- No process-global mutable Rust state or background executor.
- Native callbacks, allocation through native allocators, Zend calls and C++
  exceptions run only after the Rust call returns. No Rust borrow or frame spans
  them.

Target platforms are 64-bit Linux and macOS; both sides are compiled for the
same target.

## Policy/effect split

Most module contracts after M03 follow the same pattern:

1. Native code reads copied scalar facts, opaque identity tokens and borrowed
   initialized byte spans at the original observation point.
2. Rust returns a typed decision or next action into caller-owned output, or
   advances a caller-local POD cursor.
3. Native code performs the effect (syscall, allocation, container mutation,
   callback, Zend call, OpenSSL/nghttp2 call, context switch, exception) after
   Rust returns, then reads fresh facts before the next Rust call.

Native storage stays the single source of truth unless a contract explicitly
moves a private container into Rust; there are no shadow maps or registries.
Original ordering of errors, `errno`, warnings, partial writes and publication is
preserved. Undefined upstream behavior is not imitated with invalid Rust slices;
any correction is a named difference. Replacing a private C++ field type changes
the selected class layout, so SDK consumers must be rebuilt.

## WebSocket kernel (feature value 1, `swoole_rs_websocket.h`)

- `int64_t swr_v1_ws_frame_length(data, length, header_length)`: same query as
  upstream. Returns 0 when more header bytes are needed, -1 for overflow or an
  invalid pointer, otherwise header plus payload length. No payload bytes are
  required. `header_length` is a valid exclusive `uint32_t` output: unchanged for
  fewer than two input bytes, otherwise the required header length including
  any mask key. `data` may be null only when `length` is 0. Frame lengths that
  do not fit a signed pointer-size value are rejected.
- `size_t swr_v1_ws_write_header(payload_length, opcode, flags, output, capacity)`:
  writes a 2, 4 or 10 byte header in network order, or returns 0 without
  writing on insufficient capacity or invalid output. Flags: FIN=1, RSV1=4,
  MASK=32. Opcode is truncated to four bits; RSV2/RSV3 are cleared, as upstream.
  The mask flag does not append a key; the C++ caller appends key and payload.
- `int32_t swr_v1_ws_mask(data, length, key)`: XORs `data` in place with a
  four-byte key. Returns 0, or -1 for null/oversized input. Length 0 is a no-op
  and allows null. The key is copied first, so it may alias the payload. Byte
  alignment suffices.

All three allocate nothing, retain no pointer, invoke no callback and have no
global state. Handshake, fragmentation, control-frame policy, PHP Frame objects
and connection lifecycle stay in C++.

## Other module contracts

- Buffer queue (value 2): [buffer-abi-v1.md](buffer-abi-v1.md),
  `native/include/swoole_rs_buffer.h`. Unlike the functions above, buffer
  operations allocate; failures return statuses that the C++ facade maps to
  exceptions.
- Timer queue (value 4): [timer-abi-v1.md](timer-abi-v1.md),
  `native/include/swoole_rs_timer.h`.
- Base64, CRC32, error messages (values 8, 16, 32): [core-abi-v1.md](core-abi-v1.md).
- Other modules keep their headers under `native/<module>/`.

Feature bits are additive: buffer plus WebSocket reports 3. An overlay that is
selected without its required module flag fails at configure time.
