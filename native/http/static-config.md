# Static-serving configuration (`swr_v2_http_config_*`)

`SWOOLE_RS_HTTP_STATIC_CONFIG` is a separate capability, off by default, that
requires Rust HTTP. Neither the HTTP feature bit nor any other storage capability
turns it on. When off, the public fields, signatures, layout and native code are
unchanged.

When on, `HttpStaticConfig` is the only owner of the canonical document-root bytes,
the unique location bytes and the unique index names in insertion order. The native
`StaticConfig` facade holds one lazily allocated opaque pointer, with no cache and
no count mirror. Turning it on requires a rebuilt SDK: the old public
location/index fields and the reference-returning root accessor are removed.
Callers that mutate the containers directly or hold root references are not
supported.

## Semantics

- **Root**: published only from the initialized C prefix of the native `realpath`
  result. The input length is checked against the original `> PATH_MAX` first; PHP's
  own `>= PATH_MAX` guard stays native. Rust requests canonicalization and warnings
  (`SWR_HTTP_CONFIG_ROOT_*`), and native runs them after return. A failed
  canonicalization leaves the old root in place.
- **Locations and indexes** keep the difference between absent and initialized
  empty. Startup creates an empty location family. Indexes stay absent until the
  first one is added. Empty C++ entries are accepted and exact byte duplicates are
  dropped. PHP's empty-entry filtering is unchanged. Location order is not exposed;
  index order and dedup are.
- **Legacy path**: Rust prepares root and path and runs location matching before
  returning a native path action. Enablement flags are captured on the first step;
  later filesystem observations only replace their own bits. The directory flag is
  requested only if indexes exist.
- **V2 path**: the config, context and directory owners are queried together.
  Location/candidate iteration stays in Rust. The index count is read before a scan
  and again after it.
- **Legacy index selection** builds one local immutable span snapshot of the native
  `std::set` names. Rust copies the first configured match into the Legacy index
  result. V2 needs no snapshot.

Config/context owners and native spans must be disjoint. Mutation needs exclusive
access, just as the original containers needed external serialization. Filesystem,
canonicalization, MIME, filename and autoindex effects run after Rust returns.

The callers are the Legacy and V2 static path/index methods, the Legacy root
containment inline and both Server add methods. The root setter and startup code
are in `master.cc` (integration patch `0003-server-static-config.patch`). PHP
configuration and HTTP2 reach this through the same Server/Legacy methods.

Tests: `tests/modules/http/static_config_compat.py`, `context_gate.py`.
