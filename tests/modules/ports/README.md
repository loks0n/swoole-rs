# M25 ListenPort configuration

Contracts: [native/ports/contract.md](../../../native/ports/contract.md) and
[docs/ports-abi-v1.md](../../../docs/ports-abi-v1.md). Opt-in feature bit
8388608 (`SWOOLE_RS_PORTS`); not enabled by default.

Rust owns protocol priority/labels, integer normalization, event lookup,
listener option sequencing, socket-creation decisions, the init_protocol plan,
`get_connection_num` summation, EOF/length/stream setter normalization,
constructor defaults, callback getter/hook selection, flag/buffer/packet/option
plans, TLS/SNI frontend metadata and class-property declarations. Native code
keeps allocation, Zend storage and conversions, syscalls, callbacks, warnings,
cleanup, crypto and the receive/parser/HTTP/request-destruction bodies. No Rust
frame or borrow crosses those effects.

## Running checks

`tools/dev.py` registers most of these as `ports-*` phases. Placeholders:
`PINNED_REFERENCE` is `target/upstream/src`, `SELECTED_ARCHIVE` the Rust FFI
archive, `CONFIGURED_CORE` a configured upstream/hybrid `src` tree.

Native differential gates (extract exact original and Rust-selected bodies from
the overlay, compile both against scripted native effects, compare output):

```text
python3 tests/modules/ports/gate.py --source PINNED_REFERENCE --archive SELECTED_ARCHIVE --output REPORT [--sanitize] [--rust-asan]
python3 tests/modules/ports/listen.py --source PINNED_REFERENCE --archive SELECTED_ARCHIVE --output REPORT [--sanitize]
python3 tests/modules/ports/socket_workflow.py --source PINNED_REFERENCE --archive SELECTED_ARCHIVE --core CONFIGURED_CORE --output REPORT [--sanitize]
python3 tests/modules/ports/native.py --source PINNED_REFERENCE --archive SELECTED_ARCHIVE --core PREPARED_NATIVE_CORE --socket-io custody --output REPORT
```

- `gate.py`: integer macros, event enum/catalog and protocol plan against the
  pinned definitions.
- `listen.py`: `ListenPort::listen` bodies, 1536 traces must match.
- `socket_workflow.py`: `create_socket` bodies, 1280 traces must match. Reads
  configured Makefile `INCLUDES`/`CPPFLAGS` as literal argv; shell expressions,
  unknown variables and cycles are rejected and no Make command runs.
- `native.py`: complete native translation units plus PHP SDK syntax compile.
  `--socket-io custody` uses real loopback TCP/UDP sockets and an occupied-port
  bind failure. `--archive` skips the Rust rebuild.

Exact-body model gates share the `count.py` runner (`main()`), which extracts the
named bodies, compiles a witness against the archive and, with `--core`, syntax
checks the full original and selected `port.cc` / `swoole_server_port.cc`:

```text
python3 tests/modules/ports/NAME.py --source PINNED_REFERENCE --archive SELECTED_ARCHIVE --output REPORT [--core CONFIGURED_CORE] [--sanitize] [--rust-asan] [--openssl-root DIR] [--php-config PATH] [--sdk-origin ORIGINAL_SRC] [--include DIR]
```

| NAME | Checks |
| --- | --- |
| `count` | `get_connection_num` over shared counters |
| `settings` | EOF/length/stream setters: EOF capacity/direction, NUL bytes, every length-type byte, u16 offset truncation |
| `defaults` | `ListenPort` constructor defaults |
| `callback_property` | `getCallback` lowering using the real PHP binary's `zend_tolower_map` (read via FFI; needs `--php-config`) |
| `callback_hooks` | post-registration hook binding over all slot masks and event indices |
| `class_properties` | MINIT property declarations against inert Zend sinks |
| `flags` | non-TLS `set` prefix: flag settings and buffer clamp/fallback order |
| `packet_settings` | same prefix plus binary EOF, width and offset plans |
| `options` | same prefix through the ordinary option catalog |
| `tls_settings` | TLS option order against successful native models |
| `sni_settings` | SNI mapping admission against successful native models |

`--sdk-origin` relocates in-build include paths when compiling a private copy of
a configured SDK. On macOS pass a matching `--php-config` and `--openssl-root`.

Linux sanitizer run (builds an ASan Rust archive and reruns `gate.py`,
`listen.py` and `socket_workflow.py`, then checks that a deliberately invalid
ABI caller is caught):

```text
python3 tests/modules/ports/sanitizer.py --source PINNED_REFERENCE --core CONFIGURED_CORE --output REPORT
```

PHP runtime checks:

```text
python3 tests/modules/ports/server.py --engine hybrid=CANDIDATE_DSO --engine upstream=NATIVE_DSO [--build-manifest MANIFEST --archive SELECTED_ARCHIVE --source-ref REF] [--protocol length|eof|mqtt] --output REPORT
python3 tests/modules/ports/configuration.py --engine ... --build-manifest MANIFEST --archive SELECTED_ARCHIVE --source-ref REF [--case NAME] --output REPORT
python3 tests/modules/ports/callback_php.py --engine ... --build-manifest MANIFEST --archive SELECTED_ARCHIVE --source-ref REF --output REPORT
python3 tests/modules/ports/php.py --engine ... --output REPORT
python3 tests/modules/ports/class_properties_loaded.py --source PINNED_REFERENCE --native NATIVE_EXPORT --selected SELECTED_EXPORT --output REPORT
```

- `server.py`: starts a listener on an ephemeral port per protocol (length, EOF,
  MQTT), sends a split frame and requires the echo, callback and clean shutdown.
  `--protocol` subsets leave the gate failed. The build-manifest options
  (all three or none) verify, before startup, that the candidate DSO, archive,
  M25 Rust source, header and both patches match the manifest and that the DSO
  exports every `swr_v1_ports_*` symbol.
- `configuration.py`: setting conversion, reentry, ignored SSL, and the six
  fatal rejections, compared across engines.
- `callback_php.py`: `callback_property.php` getter fixture across engines.
- `php.py`: event registration/lookup, unknown-event warnings, Stringable
  reentry and callback replacement lifetime across engines.
- `class_properties_loaded.py`: reflection of all 19 Port properties in both
  exported DSOs against the pinned declarations.
- Upstream PHPTs for this module run in the merge tier's PHPT gate (the `phpt-*` jobs), which runs every pinned PHPT on upstream and the all-modules hybrid. To attribute a gate regression to this module, see *Attributing a regression* in [corpus/upstream/README.md](../../../corpus/upstream/README.md).

Unit tests (no native build):

```text
cd tests/modules/ports && python3 -m unittest test_configured_flags test_count_checkpoints
```

## Known failures

- `configuration.py` fails in both engines: a throwing package-length
  Stringable makes both warn and fatally reject the length type instead of
  propagating the exception. The conversion block is still native.
- `native.py --socket-io probe` fails on macOS in both engines: pre-listen
  `SO_ACCEPTCONN` returns `ENOPROTOOPT`.
- On macOS the original `heartbeat_3` PHPT (upstream TODO) and the Linux-only
  length big-packet PHPT skip, so the strict Mac originals gate stays false.
- A Rust float conversion for `max_idle_time` failed on signaling NaN with Apple
  Clang and was dropped; that conversion stays native.
- `SWOOLE_RS_HTTP_REQUEST_V2` caller adaptation has no gate here: its scripts
  depended on a `request_v2_controls.py` that does not exist in the repo.

Open: broader Server originals, getSocket/platform/real TLS coverage,
exceptions/bailout/teardown, production sanitizer runs and benchmarks.
