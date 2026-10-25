# Half-close correctness checks

The half-close correction is an opt-in native fix selected by
`tools/build_hybrid.py --fix-halfclose`. It has no Rust feature bit. It drains
queued stream/file output before graceful close, protects explicit application
pause/resume, preserves synchronous PROCESS responses across early FIN, retries
incomplete TLS close_notify, keeps sendfile ownership across EINTR, and ignores
cached read events after close is queued. See the
[native contract](../../../native/halfclose/contract.md).

## PHP server gates

Each takes one or more `--engine NAME=/absolute/modules/swoole.so`. On Linux add
`--php-extension sockets` for original selections; Mac has it built in.

```sh
python3 tests/modules/halfclose/gate.py --engine fixed=/absolute/modules/swoole.so
python3 tests/modules/halfclose/prequeue.py --engine fixed=/absolute/modules/swoole.so
python3 tests/modules/halfclose/prequeue.py --engine fixed=/absolute/modules/swoole.so \
  --workers 2 --keep-alive --max-queued-bytes 1
python3 tests/modules/halfclose/pause.py --engine fixed=/absolute/modules/swoole.so
python3 tests/modules/halfclose/pause.py --engine fixed=/absolute/modules/swoole.so --coroutines
python3 tests/modules/halfclose/pause.py --engine fixed=/absolute/modules/swoole.so \
  --tls-cert /absolute/server.crt --tls-key /absolute/server.key --tls-version 1.2
python3 tests/modules/halfclose/pipeline_concurrency.py --engine fixed=/absolute/modules/swoole.so \
  --output /absolute/report.json
python3 tests/modules/halfclose/worker_terminal.py --engine fixed=/absolute/modules/swoole.so \
  --output /absolute/report.json
```

- `gate.py`: queued graceful close for stream/file/end responses, FIN and reset,
  BASE and PROCESS. Every payload byte, one close callback, no duplicate request,
  live server.
- `prequeue.py`: early FIN against synchronous PROCESS responses; the second
  profile adds two workers, keep-alive and output pressure.
- `pause.py`: explicit application pause, early resume and resume after queued
  close, normal or coroutine callbacks. With `--tls-cert/--tls-key` every case
  requires the full payload and a strict close_notify; unexpected EOF fails.
  `--immediate-close-only` runs the empty-application-queue boundary.
- `pipeline_concurrency.py`: two pipelined requests whose callbacks must run
  concurrently; serializing them fails.
- `worker_terminal.py`: normal response control under PROCESS workers.

## Original PHPTs

Run with the official runner:

```sh
python3 corpus/upstream/run.py --manifest tests/modules/halfclose/pause-originals.json \
  --engine fixed=/absolute/modules/swoole.so --require-all
```

`normal-originals.json` and `tls-originals.json` select the normal-operation and
TLS originals the same way. `original-coverage.json` maps each unchanged
assertion to its limits; see the
[coverage review](../../../native/halfclose/original-coverage.md).

## Native method checks

These compile method bodies extracted from a prepared source tree with C++
ASan/UBSan and drive them through minimal adapters.

```sh
python3 tests/modules/halfclose/stale_read.py --source /absolute/prepared/source --output /absolute/report.json
python3 tests/modules/halfclose/sendfile_interrupt.py --source /absolute/prepared/source --output /absolute/report.json
python3 tests/modules/halfclose/tls_shutdown.py --source /absolute/prepared/source \
  --cert /absolute/server.crt --key /absolute/server.key --output /absolute/report.json
```

- `stale_read.py`: `ReactorThread_onRead` with a cached EOF after close queued.
- `sendfile_interrupt.py`: `handle_sendfile`/`catch_error` with injected EINTR,
  EAGAIN and EPIPE. Linux also interrupts a real blocking sendfile with SIGALRM.
- `tls_shutdown.py`: TLS shutdown/close methods over real OpenSSL memory BIOs and
  nonblocking socketpairs (ordering, one-way, peer-first, quiet shutdown,
  backpressure retry, peer death) plus five injected error results. On Mac add
  `--openssl-dir /opt/homebrew/opt/openssl@3`.

## Known failures

These probes exit nonzero on purpose. Do not count them as passing:

- `gate.py --probe-extra-request`: unread requests after `Connection: close`
  still reset or time out.
- `prequeue.py --probe-coroutines` and `--probe-unordered`: suspended coroutine
  responses and non-ordered dispatch are outside the fix.
- `pipeline_concurrency.py --probe-early-fin`: fails on both hosts.
- `worker_terminal.py --probe-worker-kill`, `--probe-retiring-worker-kill`,
  `--probe-worker-exit-zero`: worker death with an in-flight response leaves the
  client hanging. `--probe-worker-drain` is the graceful control.

Suspended HTTP response ownership is blocked on the worker-generation contract in
[http-response-lifetime.md](../../../docs/http-response-lifetime.md).
TLS, thread and custom dispatch are outside the synchronous prequeue fix. Mac's
original `bad_client` warning discrepancy and the expired-client `verify_02`
FAILED/WARNED result are unresolved; the latter is a terminal EPIPE alert write.
See [expired-peer.md](../../../native/halfclose/expired-peer.md).
