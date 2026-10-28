# Buffer facade lifecycle (`swr_v1_buffer_front_plan`, `swr_v1_buffer_advance`)

These additive calls sit next to the existing front/pop/release APIs; public C++
layouts are unchanged. The handle's single Rust queue also stores one borrowed
opaque identity for the native embedded front view. Rust never reads that C++
object and never calls or frees its callback or token. The old native bool slot is
kept only to preserve layout. The native facade must outlive its handle and view.

## front_plan

Returns one of:

- EMPTY, with zeroed output
- kind 1: a native token
- kind 2: a new DATA view to publish
- kind 3: the cached identity

A cached call must present the same non-null identity. Repeated reads and appends
keep the native offset, length, destroy and data changes; Rust does not republish
cached fields. Raw front reads the queue independently. Raw pop invalidates the
cache, even for an empty removal. A successful release ends the handle; a failed
pending-native release changes nothing.

## advance

Takes drain 0 (remove one) or 1 (drain), plus a fresh boolean saying whether the
cached view has a native destroy callback. Other values fail before mutation and
zero the output.

- action 0: stop
- action 1: call the cached callback while its bytes are still live
- action 2: an entry was detached; any native token is returned for deletion

`reset_view` tells native to clear its embedded data/length/size/offset after cache
invalidation. Drain batches only DATA entries that need no native effect, and
yields before every native token deletion. Requesting a callback does not mutate
the queue: native calls its noexcept callback, clears it and asks for a new plan.
After a successful pop, the cache is cleared and accounting is decremented before
the DATA Vec is freed.

Snapshots and outputs must be valid, aligned, mutually disjoint and disjoint from
the handle and storage. No reference survives a call. No reentry, concurrency,
exception, destructor or Zend escape crosses Rust.

Known difference: this path calls the destroy callback while DATA is still live,
so a callback may read DATA during destruction. That case is not compared.

Test: `tests/modules/buffer/test_facade.py`.
