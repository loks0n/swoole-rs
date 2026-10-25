# TLS/DTLS policy boundary

Opt-in feature bit 262144 (`SWOOLE_RS_TLS`). `crates/tls` takes over protocol
mask/method selection, DTLS BIO read/control/listen decisions, and the sequencing
and failure outcomes of SSL context setup. Patches `src/protocol/ssl.cc` and
`src/protocol/dtls.cc`. Declarations are in [swoole_rs_tls.h](swoole_rs_tls.h).
Tests: `tests/modules/tls/README.md`.

## ABI

All exports take copied scalars, plus bounded initialized bytes for the password
copy. No native object, OpenSSL pointer, callback or allocation enters Rust, and
Rust keeps no state. Native `long` stays native width.

- `swr_v1_tls_context(protocols, supports_dtls)` -> `{protocols, disabled, dtls}`.
- `swr_v1_tls_read(empty, front, requested, peek)` -> `{length, consume, retry}`.
  Preserves whole-datagram removal on truncated non-peek read, empty retry and
  queue-total PENDING.
- `swr_v1_tls_control(tag, observed)` -> `{long result, effect}`. Tags: 0 EOF,
  1 GET_CLOSE, 2 PENDING, 3 SET_CLOSE, 4 success, 5 GET_PEER, 6 MTU, 7 overhead,
  8 PEEK, 9 zero, others unknown. `observed` is used only for tags 0..2. Effects:
  0 none, 1 shutdown, 2 peer, 3 peek, 4 warning.
- `swr_v1_tls_listen(result)`: negative -> 0 failure, zero -> 1 pending (success),
  positive -> 2 publish. BoringSSL keeps the native `SSL_is_dtls` check.
- `swr_v1_tls_password(source, nonempty, length, destination, capacity)`: used by
  the registered password callback with the natively narrowed `int` length. Copies
  only if nonempty and `length < capacity - 1`, byte by byte (embedded NULs
  included), then writes the terminator; on reject neither pointer is touched. An
  accepted copy needs non-overlapping initialized `source[length]` and writable
  `destination[length+1]`. Negative lengths and `INT_MIN` capacity overflow are
  rejected rather than emulated.
- `swr_v1_tls_setup(stage, facts, result)` -> `{action, next}` (below).

## Setup cursor

Native code keeps a caller-stack cursor. Each call returns an action (an OpenSSL
effect performed natively after return) and the next stage. Fact bits: password 1,
cert 2, key 4, cookie 8, verify 16, http 32, boring 64, client CA 128. Action 15
`OBSERVE` performs no effect, keeps the prior result, and asks native code to read
only the field for the next stage. Facts are read lazily, stage by stage, so partial
initialization that returns early at a certificate/key/CA failure never reads
indeterminate fields. The native caller and Rust planner must come from the same
build.

| Stages | Entry point | Notes |
| --- | --- | --- |
| 0..17 | context create | password, cert, chain, key, check, cookie, capath, verify, ALPN, grease, client CA, ciphers |
| 100..103 | CA (`set_capath`) | depth observed only after CA success |
| 200..207 | ciphers | preference observed only after a nonempty accepted list; DH/curve at original points |
| 300..304 | client certificate | installs the native verify callback and depth, loads trust file, clears error queue, loads and publishes CA names |
| 400..451 | DH params | OpenSSL 3: successful `set0` transfers key ownership; install failure warns, frees key then BIO. Parse failure warns, frees BIO. Legacy OpenSSL ignores `set_tmp_dh` and frees DH before BIO |
| 500..599 | ECDH curve | capability 0 no ECDH (succeeds without reading the field), 1 list API, 2 legacy `EC_KEY` |
| 600..605 | info callback | first Socket lookup precedes renegotiation handling; accept-loop does a fresh ex_data lookup; resize result ignored |
| 700..702, 799 | DTLS `Session::init` | existing session returns false; `Socket::ssl_create` failure records last error and stops; then DTLS flag, BIO creation, `SSL_set_bio` |

The options return is normalized to a Boolean before narrowing. The curve list API
status is tested `!= 0` at full width before copying to the signed32 result.
Warnings use the native `Logger::get_pretty_name(__PRETTY_FUNCTION__)` formatter at
the original point, after Rust returns and after the error queue is popped.

`ListenPort::ssl_context_init` (`src/server/port.cc`) sets
`ecdh_curve = SW_SSL_ECDH_CURVE` ("auto") before create; PHP `ssl_ecdh_curve`
overrides it.

## Still native

- OpenSSL init/free, ex_data indices, error queue and strings.
- Info/password/ALPN callbacks run against native context/Socket/OpenSSL storage.
  ALPN output storage and negotiation stay native. The client verify callback
  returns constant 1; verification errors remain available via
  `SSL_get_verify_result` for consumers to reject.
- Client-CA X509 lists, DH/BIO/key custody, version adapters, context destruction.
- Cookie packing/HMAC and comparison.
- DTLS socket write, BIO create/destroy/method registration, Session buffers and
  queues, SSL/BIO initialization.
- Public headers, `SSLContext`/`Session` layouts, and Socket/server/PHP consumers.

OpenSSL below 1.1 is rejected at compile time.

## Native correction: BIO callback-control slot

Pinned `dtls.cc` installs OpenSSL's public dispatcher as the method's
callback-control leaf. The overlay leaves that slot unset so OpenSSL handles the
unsupported operation itself ([BIO_meth_new](https://docs.openssl.org/3.0/man3/BIO_meth_new/)).
This is a behavior change from upstream, not parity. The operation is never invoked
by tests.

## Known issues

- Upstream unsafe domains, unchanged: append bounds/OOM, negative BIO-read input,
  cookie alignment and uninitialized tail, unchecked `BIO_new` null, partial
  Socket creation failure, and uninitialized stack `SSLContext`.
- `verify_02` (expired client certificate) emits an extra native
  `Socket::ssl_shutdown` warning with the Rust engine and passes only on the
  official runner's retry (WARNED); native passes. The cause is in the Socket code.
- On macOS, separately compiled protocol TUs and the prebuilt DSO Socket use
  different ex_data indices (1 vs 0) under two-level binding, so module tests
  compile the pinned `network/socket.cc` with the protocol TUs.
- Alternate SDKs (e.g. BoringSSL) are untested; see
  [optional-config-readiness.json](optional-config-readiness.json).
