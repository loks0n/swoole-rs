# Port callers of RequestV2

Port (`src/server/port.cc`) creates, reuses, observes and deletes the HTTP request
object through the http module's pointer-only typed view (`SelectedRequestView`).
The http module owns the Rust request, its facade and the protocol/static callers;
Port owns every construction, reuse, observation, publication and deletion site.

Activation: `SWOOLE_RS_HTTP_REQUEST_V2`, used consistently by the http and Port
callers. It is off. HTTP-only and Ports-only builds use the legacy `Request`; the
two existing feature macros alone do not select V2. A Ports-only build includes the
view's legacy declarations without referencing HTTP Rust symbols.

## Adapted sites

The pinned source has 58 code-level `request->` operations on 51 lines. Only these
bodies change:

- `ListenPort::readable_callback_http`: typed allocation/reuse and access, including
  its WebSocket/HTTP2 transition cleanup calls.
- `ListenPort::destroy_http_request`: typed cast/delete at the existing point, with
  null admission and delete-before-null publication.
- Private header inclusion and compile-time type/view aliases.

| Operation | Rule |
| --- | --- |
| `new Request`, reuse cast, `conn->object` publication | Construct or reuse the selected type at the same statement; publish only after construction succeeds. |
| 14 metadata fields | Fresh getter at every existing observation; no snapshot. Preserve widths, narrowing and grouping. |
| `max_length_`, `tried_to_dispatch`, `header_length_` updates | Typed mutation at the original points; keep u32 compound-add narrowing and lazy branches. |
| `buffer_` | One native resource reference, including the initial borrowed receive buffer and the post-multipart refresh points. |
| `form_data_` presence/delete/null | Candidate discard (before a parser is installed) is distinct from multipart parser teardown. |
| Nine parser/reuse operations | Typed http-module methods with the original return values and effect order. |
| Static handler call | Legacy: existing Server member. V2: typed `Server::select_static_handler` overload. Short-circuiting and call point preserved. |

Not touched: length/EOF/Redis receive, HTTP2/WebSocket, Server/Connection layout,
TLS, PHP HTTP Context, worker generation, and `src/server/reactor_thread.cc` (its
teardown already routes through Port destruction).

## Ordering and lifetime rules

1. Object type is chosen statically. HTTP2 sets `conn->http2_stream` before
   destroying the old HTTP/1 request, and WebSocket upgrade destroys it before
   delegating, so runtime flags cannot select the type. No tag bits, address-keyed
   registry, `reinterpret_cast` or legacy-object reuse.
2. Request/connection/socket/protocol identities and the local buffer are captured
   where they are today. Field values are re-read at their original sites; no reload
   of a different request from `conn->object` after dispatch, and no new observation
   after a destruction/return edge.
3. `clean` clears only the metadata prefix before `form_data_`; it preserves
   `form_data_` and `buffer_`. The V2 reset preserves multipart state and the
   borrowed buffer and does not replace the owner with `Default`.
4. The socket receive buffer is borrowed. Close cleanup deletes
   `socket->recv_buffer` before Port destruction; teardown must not inspect or free
   it. Multipart temporary buffers and saved borrowed buffers are separate slots.
5. `delete request` precedes `conn->object = nullptr`. Native cleanup runs after
   Rust returns, with no live Rust borrow across effects.
6. `package_max_length` is read after header parsing; lazy multipart/zero-body/
   chunked branches, log strings and scalar promotions are unchanged. Returned
   request byte spans must not cross native effects.

Known limitation: code that injects a legacy `Request` into the HTTP `conn->object`
slot is not compatible with V2; the untyped pointer cannot reveal its concrete type.

Verified: five configurations (legacy, HTTP-only, Ports-only, paired, both old flags
with the capability off) compile the whole Port TU under C++14/17 on macOS and
Linux, and the view templates pass 2048 inert scenarios per host. Actual receive,
parser and request lifetime under V2 have not been executed.
