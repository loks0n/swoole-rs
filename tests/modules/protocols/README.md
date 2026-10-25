# Packet protocols and proxy codecs

`crates/protocols` implements MQTT framing, SOCKS5 wire/state/configuration
policy, RESP command/receive/reply policy and MessageBus chunking/fairness/
membership. The feature is opt-in (bit 128); the C contract is
`native/protocols/swoole_rs_protocols.h`.

## Boundaries and compatibility

Rust owns packet membership, protocol decisions and bounded encoding/decoding.
Native code owns Socket/Address execution, String/shared_ptr allocation and
lifetime, shared-memory/header layouts, logging and Zend execution. No native
allocation, destructor, PHP conversion or callback runs beneath a Rust frame.

- MQTT keeps incremental/nonminimal remaining lengths and four-byte overflow
  termination; packet type is not newly validated.
- SOCKS5 keeps state-before-send behavior, unknown-state success, byte-truncated
  domain lengths and the deferred 480-byte proxy host check. Factory credentials
  reject either field above 250 bytes and ignore both when either is missing.
  Native address-validation failures keep the three-byte CONNECT prefix.
- RESP keeps C ASCII whitespace, signed-long saturation/int32 truncation,
  null-bulk omission, permissive prefix fallthrough, full-buffer dispatch and the
  original receive counters. Native callers set errno=ERANGE after Rust returns.
  Public unbounded `get_number` remains a libc adapter.
- PHP request decoding shares the bounded Rust RESP cursor. Zend arrays keep
  nulls and integer ordering, even before the first string command.
- Handler keys use one Rust normalizer for registration, property lookup and
  dispatch: `_handler_` prefix, 63-byte truncation, embedded-NUL stop, ASCII
  lowercase.
- PHP reply encoding: PHP NIL=1 differs from native codec NIL=7. Present-empty
  status/error differs from missing; PHP empty bulk emits `$0` while the primitive
  formatter writes nothing. Embedded-NUL status/key truncation, unsigned numeric
  map keys and 32-bit map-count wrapping remain.
- MessageBus keeps direct/chunk flags, retry after minimum-size reduction, legacy
  nonnegative chunk-write success and uint16 fairness wrapping (including buffered
  receive's double increment). End wins over the fairness threshold.
- Packet owner tokens remain native-disposed; duplicate insertion rolls membership
  back and transfers no ownership.

Undefined legacy overreads/overflows are not replayed: empty MQTT asks for more,
invalid/truncated RESP fails, oversized SOCKS output is rejected before overflow.
Original malformed RESP parsing dereferences nullptr under UBSan; numeric error
cases compare the defined `get_number` helper instead. Invalid non-array PHP
SET/MAP is excluded because the original throws then dereferences invalid memory.

## Rust and native differential

```sh
cargo test --manifest-path crates/protocols/Cargo.toml --target-dir target/protocols
cargo clippy --manifest-path crates/protocols/Cargo.toml --all-targets -- -D warnings
python3 tests/modules/protocols/native.py --source /pinned/reference \
  --archive /actual/prefix/lib/libswoole_rs_ffi.a --sanitize
```

`native.py` compiles unchanged pinned function bodies and the patched overlay
bodies (`adapter.inc`, `native.cc`) with modeled String allocation/socket I/O and
compares MQTT, SOCKS, RESP, receive traces, MessageBus decisions and pool
lifecycle steps. A seeded 10,000-wire RESP corpus also runs the exact original PHP
request-parser loop with modeled Zend parameters against Rust typed events. C++
ASan/UBSan does not instrument Rust. Failing cases print trial/seed. Read-only
container mounts need `SWOOLE_RS_NO_CACHE=1` or a private native cache.

`--allocation-failures` also builds `pool_failure.cc`, which injects C++ allocation
exceptions around copy/assignment at pool sizes 0/1/31/32/33/97 and checks original
validity, shared buffers and holder cleanup. Rust allocator faults are not injected.

## Actual PHP checks

```sh
for gate in network reply request handlers bailout lifecycle; do
  python3 tests/modules/protocols/$gate.py \
    --engine upstream=/reference/swoole.so --engine hybrid=/candidate/swoole.so
done
```

- `network.py`: MQTT/RESP base/process framing and worker health, packets over
  2MiB through native 64KiB IPC, and real sync/coroutine SOCKS5 clients against a
  local scripted proxy (`server.php`, `socks.php`). No remote service.
- `request.py`: typed callbacks across base/process and coroutines on/off; nulls
  and integers before the command, overflow/truncation, empty/binary/2MiB values,
  97 parameters, mixed-case/NUL commands, 63-byte routing.
- `handlers.py`: handler lookups, property replacement/collision and diagnostic
  order over all leading/trailing byte values; invalid registrations must hit
  the original fatal exit 255.
- `bailout.py`: callback throws/exits and request-side 3MiB parameter-allocation
  exhaustion, compared across engines.
- `reply.py`: wire bytes, warnings, exceptions and callback order for replies,
  plus `reply_oom.php`, which must hit fatal allocation exit 255 during native
  reply-buffer growth.
- `lifecycle.py`: MQTT/RESP in base/process modes, eight concurrent 2MiB requests,
  exact response hashes, graceful master exit 0, no worker-error callbacks.

Known failure: on Linux all four `bailout.py` OOM scenarios fail in both original
and candidate. PHP logs allocator exhaustion, then the server stays alive and
unresponsive (base process waits in `epoll_pwait`) instead of exiting 255 or
restarting the worker. No Rust frame is active during that allocation.

## Original PHPTs

```sh
python3 tests/modules/protocols/phpt.py --source /pinned/reference \
  --engine upstream=/reference/swoole.so --engine hybrid=/candidate/swoole.so \
  --composer-autoload /private/predis/vendor/autoload.php \
  --php-extension /private/phpredis/modules/redis.so --require-all
```

Runs the 12 original MQTT/Redis/SOCKS5 PHPTs with the official runner. With both
clients, all nine MQTT/Redis cases pass; the three SOCKS cases skip because they
need an external proxy, so `--require-all` exits 1. Missing client classes are
reported unsupported, never passed.

For Predis, copy `fixtures/predis/composer.{json,lock}` into a private directory
and run `composer install --no-dev --no-scripts --no-plugins` with private
`COMPOSER_HOME`/`COMPOSER_CACHE_DIR`. PHPRedis 6.3.0 (df4fab2de7fc327c54c94a13af2b9542e4fbd720)
builds privately with phpize/configure/make; 6.2.0 does not build against PHP 8.5.

## Original core GTests (Linux)

Runs the seven unchanged `redis.*`, `message_bus.*` and `mqtt.echo` GTests against
upstream and Rust-overlay builds. Build `core.Dockerfile` on the repo dev image;
`mqtt.echo` needs Node with mqtt 4.3.8 and pino 6.14.0. Mount the repo at /repo
and pinned source at /ref read-only, private targets at /work, and a configured
Linux config.h at /configured.h:

```sh
python3 /repo/tests/modules/protocols/core.py --source /ref \
  --config /configured.h --archive /work/target/release/libswoole_rs_protocols.a \
  --build-root /work --node-modules /work/node-fixture/node_modules \
  --require-all --output /work/reports/protocols-core.json
```

It needs an isolated network (Redis 6379, MQTT 9501) and refuses an existing
Redis service. Without Node, `mqtt.echo` is unsupported and `--require-all` exits 1.

## Benchmark

`native.py --prepare-benchmark /absolute/binary` builds optimized matched bodies
from `bench.cc` and verifies checksums without timing. Run `/absolute/binary --time`
only on an otherwise idle host. The last measurement (before the borrowed-value
and PHP reply changes) showed RESP faster at every size, but the packet pool
5-13% slower at sizes 1-1024 in every pair. The pool regression and the three
original SOCKS skips block default activation.
