# V2 range-task storage (`swr_v2_http_tasks_*`)

The V2 handler keeps range tasks in one opaque Rust collection. It never uses
`core.tasks` or `core.parse_range`. The public `StaticHandler` fields, the
`parse_range`/`get_tasks` signatures and legacy callers are unchanged.

## Owner

`Vec<HttpStaticTask>` plus one scratch record per parse. Each record holds a copied
`int64` offset, a `size_t` length and 256 initialized header bytes.

- `begin` resets the scratch, like upstream's zero-initialized local task, and keeps
  entries committed earlier.
- `prepare` copies task facts and renders the part header into scratch with
  `range_response.rs`. It keeps trailing initialized bytes, truncation/NUL and
  errno-count signaling. A full-file prepare keeps the previous scratch header
  bytes, including after If-Range clears the committed tasks.
- `push` uses a fallible reserve and publishes the task only on success.
- `clear` keeps capacity and scratch.
- A null owner counts as empty for `count`/`drop`. `begin`, `prepare`, `push`,
  `copy` and `clear` need a live owner.

## Exports

`new`, `drop`, `begin`, `prepare`, `push`, `count`, `copy`, `clear`, `snapshot`.

- `prepare` takes an optional range-format descriptor and an aligned writable count,
  both disjoint from the owner. A null descriptor means full-file metadata with no
  header formatting. Invalid input returns an error and publishes nothing.
- `copy` fills one disjoint, aligned native record by value. An invalid index leaves
  the record unchanged.
- `snapshot`: capacity 0 returns the count. Otherwise every destination record must
  be constructed, aligned, writable and disjoint, and capacity must hold all tasks.
  Invalid input or too little capacity changes neither output nor `written`. On
  success it copies the values and then publishes the count.
- Rust never exports owned byte or native object pointers. Native maps allocation
  errors to `bad_alloc` after return.

## Send snapshot

`copy_tasks` builds a typed `vector(count)` and makes one `snapshot` call. The
Server uses this immutable vector for the whole send sequence, with the same
lifetime as the old native vector copy, and it may outlive the Rust owner. It is
transient IO staging, not a mirror. An exception or metadata error publishes no
snapshot. Content-type selection uses the Rust task count.

Requires a 64-bit signed `off_t`.
