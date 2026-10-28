# Upstream originals relevant to half-close

| Original | What its assertions establish | Not covered |
| --- | --- | --- |
| server/close_queued | 2 MiB + CRLF response length after ordinary close | exact payload hash, early FIN, both server modes, TLS |
| server/close_force | size predicate with heartbeat and ordinary close | an explicit force flag (never passed) |
| http_server/pipeline | ten BASE responses and server markers | suspended callback concurrency, decoded order, FIN |
| http_server/response_create | PROCESS TCP callback creates a response returning hello world | detach/adoption, retained object, session reuse |
| http_server/chunk_with_end_data | BASE reconstructed body matches image MD5 | return-value failures, FIN |
| http_server/trailer | PROCESS write/trailer/end return true; MD5 trailer matches | retention, transport EOF |
| http_server/sendfile_no_keepalive | mode 7 repeated close-header responses | exact body hash, all modes, TLS |

Run originals with PHP's official runner and the support adapter in a
disposable tree (never upstream `tests/start.sh`), with private process groups
and ports, verifying source hashes, fixtures and the exact extension.

## Constraints for a future Rust boundary

Keep one Native authority for Connection, output chunks, file progress, OpenSSL
and reactor readiness. Native read/write/sendfile/SSL, queue destruction,
callbacks and logging run after Rust returns, with no references spanning them.
Preserve cached-read rejection with TLS WANT_READ dispatch, explicit pause,
quiet/force/reset classification and EINTR's unchanged chunk/offset. No duplicate
queue, readiness flag or shadow connection registry. A Rust seam needs a
reactor/connection caller contract and real callers, not an export for one
Boolean guard.
