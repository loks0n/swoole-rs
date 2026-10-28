# TLS/DTLS boundary (M21)

Feature value 262144 (`--module tls`). Upstream targets: `src/protocol/ssl.cc`,
`src/protocol/dtls.cc`. OpenSSL 3 keeps all cryptography and the TLS/DTLS
engine; Rust binds it through `openssl-sys`.

Rust creates and configures `SSL_CTX` (every OpenSSL call in `SSLContext::create`
and its `set_*` methods), registers and implements the password, ALPN, verify and
DTLS cookie callbacks, initializes OpenSSL and owns the ex_data indexes and the
error text. Native code keeps `SSLContext`'s fields and lends Rust a view of them
per call; the password callback reads the live passphrase through a native
accessor. Warnings go through a native logger callback with upstream's text and
method name. The info callback, the DTLS Session queue, BIO method table and
socket writes stay native; the DTLS BIO read/control/listen decisions are Rust
scalar plans.

No panic crosses the ABI. Returned strings: `swr_v1_tls_error` is valid until the
thread's next call.

Upstream behavior kept:

- `SSLContext::create` fails and frees the context on any certificate, key, CA
  (with `verify_peer`), ALPN, client CA or cipher failure.
- Protocol method is chosen before zero normalization; DTLS keeps TLS 1.2.
- The verify callback returns 1; verification happens later in callers.
- DTLS: non-peek short reads drop the whole datagram; empty reads retry;
  `PENDING` is the queue total; DTLS listen return values are library-specific
  (0 pending/true, negative/false, positive listened/true).
