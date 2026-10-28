# RequestV2 (`swr_v2_http_request_*`)

`SWOOLE_RS_HTTP_REQUEST_V2` selects a Rust-owned request type. It requires both
the HTTP and Ports modules and is **off**. It stays off until the external-injection
compatibility boundary is resolved. Neither module macro turns it on by itself. The
public `http_server::Request`/`FormData` layouts and direct SDK behavior are still
available. PHP's `http::Request` is a different type and is unchanged.
Declarations are in `swoole_rs_http_request_v2.h`. The caller side is described in
`native/ports/request-v2-caller-boundary.md`.

## Rust owner

`request_context.rs` holds the request facts, flags (`SWR_HTTP_REQUEST_V2_*`),
multipart presence/active state, name/template bytes and the header/chunk/data
continuation state. It reuses the framing, header, multipart and lifecycle code
directly. Observation records are copied per call. The multipart form is
`Option<Box<Form>>`, allocated fallibly on first use. On allocation failure Rust
returns before publishing and native throws `bad_alloc`. `HttpRequestContext` is
88 bytes on the recorded targets.

`clean()` clears only the request facts and continuations. It keeps the form and
the borrowed buffer, matching the original prefix reset. Discarding a candidate
form is separate from destroying an active parser. Destroying form text and
publishing its absence are separate actions.

## Native facade

`RequestV2` has six pointer slots: Rust owner, current buffer, saved borrowed
receive buffer, owned upload String, third-party parser and captured boundary
backing. The current buffer is borrowed before parser init and owns body storage
during an active multipart request. Native keeps allocations, parser callbacks,
String/stdio, logging and errno. The captured boundary follows the original header
lifetime. The destructor never reads a borrowed buffer to infer ownership.

`LegacyRequestView<T>` and `RustRequestView<T>` hold only the typed pointer, and
each getter reads it at the original call point. `SelectedRequest` is the legacy
type unless the capability is on. The static selector is one template, called by
the unchanged legacy Server method and an additive typed overload. Each passes the
address of its private `rewrite_rules` field.

## Text for native effects

- Upload metadata: the header-value callback classifies the header name and copies
  the template into the native upload String directly from the Rust owner (bytes and
  NUL), then resets the uploaded count. The destination must have room for template
  length + 1.
- For initial upload String construction and multipart name emission,
  `text_snapshot_new` makes one immutable byte snapshot. It uses 64-byte local
  native scratch if the text fits, otherwise a fallible Rust-owned buffer
  (`text_snapshot_drop` frees it). A non-copyable, non-movable RAII guard keeps it
  alive through the String constructor or append call. Empty text gets an
  initialized NUL.
- `text_set` reuses the existing capacity of each Vec: it reserves before clearing,
  so the previous value survives an error.

No Rust borrow or pointer into live form storage crosses a native effect.

