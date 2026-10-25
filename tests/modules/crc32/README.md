# CRC32

ABI: `docs/core-abi-v1.md`, `native/include/swoole_rs_crc32.h`. Opt-in feature
bit 16. The overlay removes the whole algorithm from `src/core/crc32.cc`; the
native `swoole_crc32` entry point forwards borrowed bytes to Rust. Omit the
overlay to keep the original for comparison.

The Rust crate implements reflected IEEE CRC32 without allocation or mutable
global state. With `target_arch=aarch64` and `target_feature=crc` it uses the
IEEE `__crc32d/w/h/b` intrinsics (not CRC32C) on 8-byte chunks and 4/2/1-byte
tails; other targets use a compile-time slicing-by-eight table (8 KiB) with
explicit little-endian loads. The target contract selects the implementation;
there is no runtime CPU probe. Unlike the pin's mutable table (whose
`generated` flag is never set) there is no initialization race. The primitive
rejects address-space wrapping before building a slice; that is outside
upstream's defined domain, not a compatibility fix.

Derived from Swoole v6.2.4 (`c7e514509451beafd4d70ce5b78943d51e76381c`),
Apache-2.0; the native source keeps the original notice.

The pin's only production caller is `src/server/reactor_thread.cc`, which
hashes `Address::get_addr()` with the `sockaddr` length (28 bytes for IPv6) to
pick the worker for non-IPv4 datagrams. PHP `crc32()` uses PHP's own
implementation and does not exercise this code.

## Differential

```sh
cargo test -p swoole-rs-crc32
```

`crates/crc32/tests/upstream.rs` compares `swr_v1_crc32` with the pinned
`src/core/crc32.cc` (vendored unchanged in `crates/oracle/upstream/`, symbol
renamed) on the empty input, every one- and two-byte input, every length up to
64 and proptest input up to 4 KiB, each at seven unaligned offsets. It also runs
the original `TEST(hash, crc32)` from `core-tests/src/core/hash.cpp` against the
adapter `crates/oracle/build.rs` rebuilds by applying the overlay patch to the
vendored original.

## Consumers

`consumer.py --extension EXTENSION --manifest IDENTITY --output REPORT` starts a
real Swoole UDP6 server in process mode (`consumer.php`) and checks that 56
binary messages from eight clients reach the independently computed CRC32
worker, and that eight empty datagrams get no callback (pinned recvfrom's
`ret <= 0` branch).

`address_span.py --source PINNED_REFERENCE --native-report NATIVE_CORE_REPORT
--output REPORT` uses a completed native-core build library and checks six real
`Address` spans against pinned C++ (`address_span.cc`). Known caller behaviour
it documents: fresh `::1` gives CRC 2630436834, but 814556344 after the same
thread formats a longer IPv6 address; a fresh thread starts zeroed and fork
inherits the previous tail; short filesystem Unix recvfrom exposes two
preexisting tail bytes. Rust matches C++ for every span.

## x86_64

`x86_probe.rs` includes the production source unchanged in a freestanding
x86_64 Linux ELF that exits nonzero on any failed check. Build it with
`rustc --target x86_64-unknown-linux-gnu`, `-C panic=abort`, static relocation,
rust-lld and link args `-nostdlib -static -no-pie`, then run it with
`python3 tools/linux_dev.py -- /repo/target/NAME` (binfmt emulation).

## Known gaps

- Not measured: no throughput numbers exist for the current backends (#31).
- Linux has not run the current slicing-by-eight and instruction backends.
- Native x86 hardware, maximum/abstract Unix path spans and uninitialized
  production padding in callers are untested.
