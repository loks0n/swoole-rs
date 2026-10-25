# Legacy directory store

`SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE` is a separate capability, off by default,
that requires Rust HTTP. When off, `StaticHandler` keeps its private
`std::set<std::string>`. When on, that field becomes `LegacyDirectory`: one typed,
unique Rust owner with explicit reserved bytes and size/alignment guards that
match the set's slot. Nothing is reinterpreted and there is no global side table.
Public methods, task vector, String/MIME references and Server fields are unchanged.

## Callers

- `get_dir_files` copies each name with `swr_v2_http_directory_scan_append` before
  the next `readdir`. After `closedir`, `scan_finish` sorts and dedups in place.
- `try_serve_index_file` keeps the configured priority order.
- `make_index_page` renders the owned names through the shared append operation
  (see [directory-v2.md](directory-v2.md)).
- With `SWOOLE_RS_HTTP_STATIC_CONFIG` on, the Rust config and directory owners are
  intersected directly.

## Lifetime

- Empty storage stays unallocated.
- Copy construction deep-copies every name before publishing the new owner. Copy
  assignment builds a temporary and swaps. Moves transfer ownership and leave an
  empty, reusable value.
- If an append fails mid-scan, the names copied so far are finalized before native
  error translation.
- Native translates allocation status after Rust returns. Every reserve/extend,
  directory IO call and exception happens after the Rust call completes.

## ABI

The slot geometry and declaration position match the set, but this is **not**
binary-compatible with an SDK compiled for the set. Turning the capability on
requires rebuilding the SDK.

Tests: `tests/modules/http/legacy_directory_gate.py --source PIN --archive ARCHIVE
--output JSON` (value and extracted-method checks, no real filesystem) and
`legacy_directory_compat.py --source PIN --output JSON` (C++14/17 syntax and
member layout for the off, on and combined modes).
