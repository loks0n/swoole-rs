# TLS/DTLS policy boundary (M21)

Feature value 262144 (`--module tls`). Upstream targets: `src/protocol/ssl.cc`,
`src/protocol/dtls.cc`. OpenSSL (or a compatible library) keeps all
cryptography and the TLS/DTLS engine. Follows the
[policy/effect split](abi-v1.md#policyeffect-split).

Rust decides protocol/option/setup/failure policy and BIO read/peek/consume/
control. Native code makes every OpenSSL call, logs, allocates, frees and
registers callbacks. OpenSSL can call password/info/ALPN/cookie/BIO callbacks
synchronously, so no Rust frame surrounds a native call that might throw, bail
out, switch context or tear down its owner. Callback bodies may call Rust leaf
policy separately.

Native code keeps global initialization, ex_data indexes, context/session and
`BIO_METHOD` ownership (destroy/re-init is not `OnceLock`), SSLContext storage,
the Session deque/Buffer, `BIO_data` and the lazy BIO method. `SSL_free` happens
before session/map erase so BIO callbacks work during free. Returned strings and
ALPN output keep native lifetime. Error-queue popping and errno order are exact.

Upstream behavior kept:

- `SSLContext::create` returns true when the certificate file fails to load, but
  false for other key/chain/check failures.
- Protocol method is chosen before zero normalization.
- The verify callback returns 1; verification happens later in callers.
- TLS 1.2 cipher list and TLS 1.3 ciphersuites are handled separately.
- Option values follow the linked library version; OpenSSL 3 is not assumed.
- DTLS: non-peek short reads drop the whole datagram; empty reads retry;
  `PENDING` is the queue total; DTLS listen return values are library-specific
  (0 pending/true, negative/false, positive listened/true).

Cookie-secret cases are compared only where the secret is aligned and initialized.
