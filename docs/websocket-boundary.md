# WebSocket (M02)

The overlay replaces three operations in `src/protocol/websocket.cc` with the
Rust kernel from [ABI v1](abi-v1.md):
frame/header-length query, wire-header writing and payload masking. The
duplicate C++ implementations are removed in the overlay; omitting it keeps the
pinned code.

Still upstream C++:

- `encode`: String allocation, mask-key insertion, body copy around the Rust
  header writer.
- `decode`: frame metadata, complete-frame check, payload selection, then the
  Rust mask call. PHP `unpack` rejects input shorter than the native header first.
- `pack_close_frame`: close code/reason bounds.
- `dispatch_frame`: fragment accumulation, message-size limits, opcode
  decisions, control dispatch, close response.
- `ext-src/swoole_websocket_server.cc`: handshake, PHP Frame mapping,
  compression, automatic ping responses, disconnect lifecycle.
- Generic protocol/reactor code: receive buffering, package limits, readiness,
  writes, socket close.

The ABI has no decoded Frame struct or fragmentation state.

## Pinned invalid-frame policy

From Swoole v6.2.2 (`tests/modules/websocket/invalid.py` checks these on both
engines, 20 scenarios):

- `dispatch_frame` rejects a continuation with no fragment buffer, and a second
  unfinished text frame while one is pending.
- Ping/pong rejection compares total wire length against
  `sizeof(buf) - SW_WEBSOCKET_HEADER_LEN` = 127. Masked payload 120 passes; 121,
  125, 126 terminate. Unmasked 124 passes; 125, 126 terminate. These are not the
  RFC control-frame limits.
- A small ping with FIN=0 is accepted; default ping handling replies with a
  FIN=1 pong.
- Fragment accumulation fails only when the summed payload exceeds
  `protocol.package_max_length`. Native startup clamps that setting to at least
  65536 (`src/server/master.cc`, `include/swoole_config.h`). Totals of 65535 and
  65536 echo intact; 65537 terminates.

## Tests

- `tests/modules/websocket/kernel.cc`: every header prefix, 7/16/64-bit length
  boundaries, all opcode/flag bytes, unaligned buffers, signed-size overflow,
  short outputs, XOR involution, overlapping keys.
- `prefix.py --sanitize`: Rust vs the pinned C++ length function over 2,688
  header prefixes, all eight alignments, masked/unmasked, four keys. Four
  overflow inputs are Rust-only, since upstream has signed overflow there.
- `differential.py`: upstream vs hybrid on 58 FIN/mask frames (lengths
  0/1/125/126/127/65,535/65,536) plus PHP string/object lifetime and pack-only
  RSV1 control cases (778 total): packed bytes, payloads, flags, close fields.
  No invalid frames.
- `close_probe.py`: coalesced frames, header/body write splits at 125/126/65,535/
  65,536, fragmented text with interleaved ping/pong, close and EOF. Write splits
  do not guarantee receive splits; `prefix.py` is the deterministic length check.
- Corpus `06-websocket`: handshake accept hash, broadcast to two clients, masked
  close; requires an unmasked two-byte FIN+CLOSE reply with status 1000 and EOF.
- Original PHPTs: 15 of 34 in `tests/swoole_websocket_server/` are selected.
  `--module websocket` selects `pack` only; add `--module websocket-network` for
  the socket cases. `send_close_frame` fails on both engines.
- Autobahn: see [validation](validation-suite.md#autobahn).

Not covered: server-initiated or simultaneous close, close reason echo,
fragmented or oversized control frames, non-minimal length encodings.
