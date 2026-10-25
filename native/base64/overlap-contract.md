# Base64 encoder: overlapping buffers

The public `include/swoole_base64.h` declarations do not forbid overlapping
input and output (no `restrict`). The pinned encoder in `src/core/base64.cc`
interleaves input reads with output stores, so with an alias a later read can
see an earlier store. The Rust encoder keeps the existing C export signature and
reproduces that behavior.

## Implementation

- Byte extents are checked, then classified as disjoint or overlapping before
  any Rust reference is created. Integer addresses are used only for this
  classification; all reads and stores go through the caller's original
  pointers.
- Disjoint buffers use the scalar encoder and, on little-endian AArch64 with
  NEON, 48-byte vector blocks.
- Overlapping input uses allocation-free raw byte operations in the pinned
  statement order (`base64.cc` lines 63-95):

| Native statement | Rust operation |
| --- | --- |
| case 0: read current byte, one store | match arm 0, alphabet store |
| case 1: read previous/current, one store | match arm 1, alphabet store |
| case 2: read previous/current, first store | match arm 2, alphabet store |
| case 2: reread current byte, second store | separate `if i % 3 == 2` read/store |
| reread final input byte, padding stores | `last % 3` match after the loop |
| terminating NUL, return count | final raw store, then `written` |

The second read in case 2 follows the first store, and the final padding read
follows all loop stores. There is no input snapshot, rejection or native
fallback. For example, encoding in place at the same address gives `AQ==` for one
zero byte and `AQEF` for three zero bytes. Empty input keeps the existing Rust
behavior (writes a NUL).

The decoder is unchanged and still requires disjoint buffers. The supported
contract in `docs/core-abi-v1.md` allows valid, initialized, positive-length
overlaps for the encoder only.

## Known callers

The four pinned low-level encoder callers all use separate buffers:

| Caller | Input | Output |
| --- | --- | --- |
| `HttpProxy::get_auth_str` | `auth_buf[256]` | `encode_buf[512]` |
| `Client::set_basic_auth` | local `std::string input` | separate `emalloc` result |
| `swoole_websocket_handshake` | `sha1_str[20]` | `sec_buf[128]` |
| `String::append_random_bytes` | String allocation | separate `new char[]` |

Overlap behavior is tested against a pure Rust model only, not against the native
encoder.
