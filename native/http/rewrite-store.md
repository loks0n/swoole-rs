# Server rewrite-rule store (`swr_v2_http_rewrite_store_*`)

`SWOOLE_RS_HTTP_REWRITE_STORE` is a separate capability, off by default. When on,
the private `RewriteRules` field owns one opaque Rust handle, and a second
always-null slot keeps the original field size. No `shared_ptr` is read or
reinterpreted. The public `RewriteRule` type, Server methods and configuration
are unchanged. When off, the original `shared_ptr`/vector path is used. An unknown
field size or alignment is a compile-time error.

## Catalog

- One byte arena plus ordered offset records. Each record holds its pattern and
  replacement span, the split point and a regex flag. Patterns are trimmed.
  Duplicates, empty rules and binary bytes are kept in insertion order.
- Append reserves byte and record capacity before publishing. On reservation error
  the existing entries are unchanged, though capacity may have grown. The owner is
  published lazily, after the first complete admission. Native maps allocation and
  size errors to `bad_alloc` after return.
- All the bytes must fit in one allocation bounded by `isize::MAX`.
- The owner is dropped during normal member destruction at the field's original
  declaration position.

## Callers

Both legacy `apply_rewrite_rules` and `StaticHandlerV2` read the private field at
the existing rewrite point and send their current action to the catalog. Rust
handles classification and consecutive literal misses in one call, and returns at
a native regex search, native output allocation/fill, completion or error.

- Literal match and replacement read the owned bytes inside Rust. Legacy gets the
  query/fill result in native output storage. The V2 context accepts the rewritten
  bytes directly. An empty or byte-identical literal match still publishes and stops.
- A regex rule copies only its pattern before native regex construction. The
  replacement is copied only after a successful search. A regex result equal to the
  input continues to later rules. Unmatched regex rules never copy the replacement.
- Legacy query errors are treated as an unmatched rule. Owned literal errors keep
  the native allocation-error mapping.
- `RewriteRules::at` returns a complete `RewriteRule` copy for inspection. Neither
  caller uses it on the rewrite path.

Tests: `tests/modules/http/rewrite_store_gate.py` (with `--prepare-binary PATH` it
also builds untimed workload binaries that support `--check-workloads` and
`native|rust WORKLOAD ITERATIONS`), `rewrite_store_compat.py`.
