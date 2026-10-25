# HTTP/2 boundary (M24)

Feature value 4194304 (`--module http2`). Upstream targets:
`src/protocol/http2.cc`, `ext-src/swoole_http2_server.cc`,
`ext-src/swoole_http2_client_coro.cc`. Frame/Settings/Session/Stream/Context
layouts and PHP declarations are unchanged. Follows the
[policy/effect split](abi-v1.md#policyeffect-split).

Rust owns settings, frame, header, stream, request/response, window, chunk and
control policy. HPACK/nghttp2, Zend values, native Context helpers, sockets,
crypto, compression and I/O are native effects. One native `default_settings`,
server session/stream maps and client stream map/settings/windows remain. The
empty `server_ips`/`client_ips` maps are unused.

- Settings unpack calls a native callback per item and keeps stop/error
  behavior, rereading bytes and defaults after each mutation. Zero or negative
  signed length returns success. A partial final item is not rejected when the
  original buffer permits the read; there is no `length % 6 == 0` check and no
  eager decode. One original native test passes the whole frame length to the
  payload decoder; it is kept.
- Kept: role-specific settings/HPACK effects, unknown-setting handling, unsigned
  windows, send/chunk/end order, header locale/case/CRLF/trim, PHP cookie
  encoding, nested headers and compression defaults, client RST/GOAWAY, ignored
  PUSH_PROMISE, stream-id and pipeline publication, queue limit/pop/release/
  error order. Incomplete upstream CONTINUATION/push/coroutine-window support is
  left as is.

## Client send queue

The private `std::queue<zend_string *>` in the Client
(`ext-src/swoole_http2_client_coro.cc`) is one Rust `VecDeque` of opaque tokens
owned by a non-copyable native member and released after native close/destruction.
Each call borrows the container only for that call. Dropping it frees only token
storage, never Zend strings. Creation and growth are fallible; native throws
after return. Zend string creation precedes push; FIFO/peek across send,
pop-before-release and the strict queue limit are kept. Allocation counts and
capacity differ from `std::deque`.

Known gap: a native bailout that skips C++ destruction also skips releasing the
container.

Original inventory: 70 PHPTs (44 direct HTTP/2), 5 direct and 5 cross native
tests. HPACK is embedded 1.64.0 or external nghttp2.
