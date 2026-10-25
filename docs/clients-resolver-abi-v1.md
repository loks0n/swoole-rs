# Clients and resolver boundary (M22)

Feature value 1048576 (`--module clients`). Upstream targets:
`src/network/{address,client,dns}.cc`, `ext-src/swoole_client.cc`,
`swoole_client_async.cc`, `swoole_client_coro.cc`, `swoole_name_resolver.cc`,
`swoole_http_client_coro.cc`. `include/swoole.h` and `include/swoole_client.h`
(Client/Stream layout, inline bodies) are unchanged. Follows the
[policy/effect split](abi-v1.md#policyeffect-split); data crosses as `repr(C)`
scalars, opaque tokens, borrowed spans and caller-owned output with checked
capacity.

## Address parsing

- Rust makes regex/grammar/family/port/path decisions. C-string/NUL handling,
  errno, narrowing and exception order match upstream. The type is published
  before failure, as upstream. Unix socket length/path rules are kept.
- Loopback is the exact string `127.0.0.1`, not `127.0.0.0/8`.
- Numeric IPv4/IPv6 parsing runs on copied bytes up to the first NUL. The caller
  picks the platform grammar: Apple accepts leading zeros in IPv4 and in IPv6
  dotted tails, Linux rejects them. Scoped IPv6, DNS, unsupported-family errno,
  sockaddr writes and `inet_ntop` stay native.

## Resolver

Rust selects codec, hosts file, resolv.conf, query, result and error handling on
bounded snapshots, keeping tokenization/locale, comments, alias and first-result
order, family coercion and invalid-port fallback. c-ares, addrinfo/hostent
allocation, channel/socket maps, timers, cancellation and coroutine callbacks are
native. `SwooleG.name_resolvers` stays the single registry; M07 owns the DNS LRU.

## Clients

Rust decides address/proxy precedence, connect/retry, handshake, read/error/
timeout, shutdown/watermarks, persistent reuse and PHP property/argument order.
SOCKS5 rewriting happens before HTTP proxy rewriting. `onClose`, `onReceive`,
`onBufferFull`, `onBufferEmpty` and `onError` may reenter, close, delete, throw or
bail out; after `onClose` may delete the Client, only the saved Socket's
object-null guard permits further access. The destructor clears
`Socket::object` before deferred free; timer cancellation precedes `onConnect`.

Persistent connections: the private `long_connections` map of heap queues in
`ext-src/swoole_client.cc` is one Rust-owned pool with binary keys and FIFO
queues of opaque Client tokens (take/push/remove-if-empty). It is created lazily
at the original allocation point and uses a deterministic hasher (no
`RandomState` entropy). Allocation is fallible; native throws `bad_alloc` after
return. Dropping the pool frees only Rust containers, never Client tokens.
Upstream never reclaimed residual queues at teardown; Rust does.

Original inventory: 104 raw-client, 2 resolver, 89 HTTP coroutine-client and 18
cross-family resolver PHPTs.
