# Cookie scratch and callback flow (`swr_v2_http_cookie_flow`)

`cookie_flow.rs` handles scratch admission and growth, rebasing source offsets,
overlap-safe copy with NUL initialization, token iteration (reusing the cookie
tokenizer) and stopping on the callback result. `HttpCookieFlow` is call-local
state holding copied offsets only: no pointer, no resource and no heap allocation.

Two native callers:

- `http_cookie_scratch`: copy only, for the legacy and V2 multipart filename paths.
  Delimiters are left intact for the filename parser.
- `parse_cookie`: full iteration. It stops before tokenizing the next record when
  the callback returns false.

Each caller captures its thread-local scratch object and reads that object's
current backing and capacity again after each effect. Native runs the reserve,
callback, exception and argument-pointer handling after Rust returns. Callback
records are copied offsets, and a missing value still uses the original empty
literal. Rust rejects unrepresentable spans and an inconsistent resumed
length/capacity before copying.

Tests: `tests/modules/http/cookie_flow_gate.py` (compares callback sequences and
scratch bytes with the pinned `parse_cookie`, and supports `--rust-sanitize` on
Linux).
