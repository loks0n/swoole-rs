# ListenPort and PHP Port boundary (M25)

Feature value 8388608 (`--module ports`). Upstream targets:
`src/server/port.cc`, `ext-src/swoole_server_port.cc`. Follows the
[policy/effect split](abi-v1.md#policyeffect-split).

Rust owns callback-free policy: native defaults, protocol selection,
listener/option/setup policy and PHP Port settings. Sockets, socket options,
OpenSSL (including SNI name matching and DTLS), Zend conversion, object/property
custody, allocation, logging and callbacks stay native, as do the callback, SNI,
session and connection containers. Return values, errno, warnings, partial
publication and cleanup order match upstream.

Native and unchanged: receive callbacks, `readable_callback_*`,
`destroy_http_request`, HTTP dispatch and parser continuation, worker generation
and suspended-response handling.

HTTP RequestV2 (`SWOOLE_RS_HTTP_REQUEST_V2`, off by default): with M04's Rust
request, `readable_callback_http` and `destroy_http_request` use typed
allocation/reuse/access/delete while every receive, dispatch and lifetime
decision stays native. The HTTP/2 stream flag does not choose the deletion type.
Cleanup keeps multipart and borrowed buffers, and teardown never touches the
socket buffer M08 has already released. A ports-only build must compile without
HTTP Rust symbols.
