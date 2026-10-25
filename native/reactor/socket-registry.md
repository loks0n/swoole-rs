# Socket registry (`SWOOLE_RS_REACTOR_SOCKETS_OWNED`)

OFF unless requested. Default/OFF keeps the Native `std::unordered_map` and the
const-reference `get_sockets()` API.

## Ownership and callers

Rust owns key membership, Socket identity values, stable linked-node order and
independent snapshots. Freed node slots are reused with checked generations. The
default owner is null/lazy; nothing is allocated at module load. Reserves are
fallible and Native translates the status after return. Rust never dereferences,
closes, frees or drops a Socket token.

- The inline `exists/get/count/foreach/_add/_exists/_del` methods use the store.
- `get_socket` keeps `operator[]` semantics: a missing key inserts null and
  changes the count; `contains` is then true.
- `_add` publishes Socket events/removed first, then reads fd for publication.
  `_del` keeps its Native field prefix before erase. `_set` only writes Socket
  events.
- ON adds `socket_registry_view` and `socket_registry_snapshot`; the const map
  reference is unavailable (no fake map, mirror or layout punning).
- Poll requests an owned snapshot before reset and still reads each Socket's
  fd/events. Admin uses the live range and count API.
- `foreach` callbacks run after Rust returns.

The live view keeps a stable owner-slot identity, so lazy publication is visible
to an earlier empty view. Each advance requests fresh links and returns a copied
fd/token pair. Deleting the current node invalidates the iterator, as with the
Native map. A snapshot owns copied metadata only and never extends a Socket's
lifetime.

## Iteration order

The Native map order is observable, so the Rust store must reproduce it.

**Apple (libc++ 210106, ABI 1).** Native ON requires that platform/version/ABI,
64-bit `size_t` and 32-bit `int`. The constructor checks
`swr_v1_reactor_sockets_policy()` against the linked Rust implementation: 1 for
the Apple backend, 0 for the unqualified fallback. Unknown policy is refused.

Derived from libc++ `__hash_table` and `unordered_map` copy construction:

- Key is cast from signed int to `size_t` before modulo.
- New keys prepend inside an existing bucket, or at the global head for an
  empty bucket. Overwrite keeps position. Erase keeps bucket capacity.
- Rehash keeps a bucket's first contiguous run and moves later runs to that
  bucket's head.
- Growth: float load comparison at `max_load_factor` 1, `2*bucket_count` plus
  the non-power-of-two adjustment (including the special 2 case), prime or
  power-of-two bucket selection. Rust uses checked arithmetic.
- Copy order: start empty at the source bucket count, then reinsert in source
  live order.

Lookup uses the contiguous bucket groups; one count tracks live entries. There
is no separate hash index.

**GNU libstdc++ 12 candidate (Linux).** Same node/bucket store with a const
policy parameter. Integral hash casts to `size_t` and divides by bucket count.
Initial bucket policy 1 / next-resize 0 grows to 13 on first insertion; later
growth uses the release prime table, double min-bucket calculation and twice the
current count. The cached threshold is reconstructed: 0 when empty,
`floor(double(bucket_count))` at load 1, `SIZE_MAX` at the terminal prime.
Insertion prepends within a nonempty bucket or at the global head. Unique rehash
reinserts every node, including the first run. Copy preserves source next-link
order. **Native Linux ON is still refused**; unknown platforms use the old
insertion-order fallback.

`sockets_gnu_source.py --candidate-dir READONLY_CAPTURE --report UNIQUE.json`
compares the candidate to the official GCC 12.2 source bodies (8 definitions,
304 primes) taken from a read-only capture of the Debian
`libstdc++-12-dev 12.2.0-14+deb12u1` headers.

## Iterators

Live and snapshot C++ iterators use inline Rust C POD state (56-byte live,
16-byte snapshot). Rust owns advance, postfix copy, comparison and snapshot
lookup. Native reads the owner slot, materializes `std::pair<int, Socket *>`,
returns C++ references and aborts only after Rust returns. Constant aggregate
seeds keep default construction, `noexcept` and trivially copyable traits.

## Compatibility

ON changes the private class size (selected OFF 1008 B vs ON 976 B on the
captured SDK; all public offsets unchanged) and C++ source compatibility: no
const map reference, and the owner is noncopyable. Consumers need a rebuilt
selected SDK. Allocator, bucket, iterator/reference and external binary
compatibility are not provided.
