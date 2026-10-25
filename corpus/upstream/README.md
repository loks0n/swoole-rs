# Original upstream Swoole tests

This selection runs **69 original PHPT tests** from Swoole **v6.2.2**, commit
`8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e`. The manifest records each source path,
SHA-256, subsystem, and required PHP APIs. The PHPT files are extracted with
`git archive` from the pinned Git object and checked against these hashes before
execution. Local checkout edits cannot silently change the selected tests.

The selection covers incremental HTTP request parsing, channel payloads/closure/
stats, typed Table rows and deletion, timer ordering/cancellation, coroutine
lifecycle/defer, atomics, and WebSocket frame encoding/decoding. All 33 original
WebSocket tests exercise receive decoding, send encoding, fragmented messages,
ping/pong, malformed data, close flags/status/reasons, handshake token order
and callback/property registration. Some retain upstream randomized server modes
or close-code branches; failures are recorded without retries to green. Network cases use ephemeral local loopback
listeners; no external databases or internet services are required. The frame test includes
1,000 randomized round trips with invariant assertions; this is not the whole
upstream suite and does not replace its larger regression/stress suites.

```sh
python3 tools/build_upstream.py
python3 corpus/upstream/run.py \
  --engine upstream=target/upstream/src/modules/swoole.so --require-all
python3 corpus/upstream/run.py \
  --engine hybrid=target/hybrid/rust-buffer-websocket/modules/swoole.so
# Target a migration module:
python3 corpus/upstream/run.py \
  --engine upstream=target/upstream/src/modules/swoole.so --module timers --require-all
```

`--engine` is repeatable; `--php` and `--php-extension` behave like the application
corpus runner. `--source` selects an existing checkout at exactly the pinned
commit. `--module` is repeatable; groups are `http-request`, `channels`, `table`,
`timers`, `coroutines`, `atomics`, `websocket`, and `websocket-network`. Unknown/empty selections fail.
On systems with dynamic modules, load `pdo`, `pdo_sqlite`, `curl`, and `sockets`
uniformly through repeatable `--php-extension` flags. Built-in macOS modules
need no flags; duplicate module warnings can affect exact PHPT outputs.
The builder supplies `run-tests.php` via `phpize`; its checksum is recorded in
the report alongside the PHP version. This generated runner is not a Swoole Git file.

Tests execute through **PHP's official `run-tests.php` PHPT runner**, supplied by the matching PHP installation through `phpize`, in a
disposable tree. PHPT `FILE`, `SKIPIF`, expected-output sections, assertions, and
the official PHP runner itself are unmodified. Swoole's custom runner is intentionally
not used: it contains failure cleanup that can kill unrelated listeners by port.
The wrapper instead cleans up only each test's isolated process group. Its `-W` result ledger is parsed; only `PASSED`
counts as a pass. Failures, unexpected statuses, runner errors, and timeouts fail
the command. Unsupported APIs are reported separately; `--require-all` also
fails on unsupported and skipped cases. Rust currently cannot run this selection
because its APIs and upstream bootstrap prerequisites are missing. Those 69
unsupported results are compatibility gaps, not passes.

There are two explicit **test-support adaptations** in the disposable copy:

1. A small PSR-4 autoloader loads original `SwooleTest` helpers instead of installing
   unrelated Composer dependencies. Selected tests do not use those packages.
2. The original bootstrap's unrelated remote-object daemon initialization is
   removed. It otherwise attempts to write under HOME and start a daemon even for
   an atomic/codec unit test. The adapter requires the exact expected setup block
   and fails closed if it changes. All actual test bodies and assertions remain.

Reports record the pinned commit, original support Git tree, unchanged runner
checksum, effective adapted-bootstrap checksum, and adapter description. HOME
and TMPDIR point into the disposable tree. Each test process group has an outer
timeout and is terminated with its children, including on failure. This is
process/filesystem isolation for the selected trusted tests, not an OS security
sandbox. Bootstrap-dependent tests explicitly declare `upstream_test_bootstrap`
as well as their subsystem capabilities. Network cases additionally probe
`coroutine_http_client` or `coroutine_tcp_client`; raw synchronous helpers require `sync_tcp_client`,
plus `php_sockets` for
the helper’s socket calls; if these APIs exist but misbehave, tests
run and fail normally.

JSON defaults to `target/reports/upstream-phpt.json`. Adjacent `*-artifacts/`
directories retain runner logs, its result ledger, and available expected/actual/
diff/generated-PHP files per engine/test. Tests are never blessed or rewritten to
match the prototype. Source is fetched rather than vendored; upstream copyright,
license notices, helpers, and license file are preserved in the disposable copy.

The expanded selection currently exposes `send_close_frame.phpt` failing with
empty output versus expected `lalalala` on both upstream and hybrid, on macOS
and Linux. It remains registered and failed, with original assertions intact.
Its parent kills the server immediately after two sends; teardown timing is a
hypothesis, not a confirmed diagnosis.

The expanded audit registers all 33 original WebSocket PHPTs, plus timer `info`,
`stats`, `clearAll`, `after_fork`, `reinit_1` and `reinit_2`. Original timer assertions
run through the official runner before any M03 rewrite. `memory.phpt` retains its original
`skip_if_no_top()` and is counted as skipped on macOS; skips never become passes.

Module owners can pass `--manifest /absolute/selection.json` to select additional
original PHPTs without changing the central selection. Use the same pinned
`commit` and test fields (`path`, `sha256`, `module`, `requires`). Original bytes
are checked from pinned Git objects; capability failures and strict skip handling
are unchanged. Reports record the selection path and SHA256. New selections do
not expand the runner's audited parallel-safe allowlist.

Owned selections may include `support_files: [{"path": "examples/test.jpg",
"sha256": "..."}]`. The runner extracts those files from the same pinned Git
commit, verifies their hashes before executing tests, and records the declarations
in the report. Paths must be relative repository files. Working-copy assets are
ignored; a missing asset or checksum mismatch fails the run. This adds fixtures
without modifying the original PHPT assertions or capability probes.

The separate `versioned.py` profile supports the pinned upstream `_85` expectation
sections using the exact `PHP_VERSION_ID >= 80500` selection in `tests/run-tests`.
It reads that file only to verify the frozen rules hash; execution still uses the
matching installation's official PHP runner. Original FILE/SKIPIF/other bodies
and the selected expectation body are byte-identical. Receipts include original
and adapted PHPT hashes, protected-section hashes, selected body hash, PHP version,
actual extension and official-runner identities. PHP8.5 uses explicitly recorded
`fatal_error_backtraces=On` to match the pinned stack-trace expectation.

`framing-versioned-expectation` is an additional, explicitly adapted diagnostic
for `wrong_eof_setting.phpt`. The normal complete framing inventory remains
untouched and retains every first failed/skipped/warned/unsupported outcome. A
passing adapted case is not a passing untouched original or whole inventory;
those report fields stay false. Unknown/duplicate or competing assertion sections
are not silently discarded to get a pass.


`tree.py --source PINNED --group swoole_stdext --module phphelpers --requires
stdext --output PRIVATE_MANIFEST` inventories every original PHPT and support
blob from the pinned tree, without exclusions or assertion changes. It rejects
changed tracked originals/support, wrong source heads and traversal groups.
The shared Git blob reader batches content extraction. The31 stdext cases require
actual loaded stdext functions; disabled builds report unsupported. A syntax-only
SDK profile does not establish actual stdext runtime support. The canonical
`tools/dev.py integrate --module phphelpers --stdext` plan builds separate genuine
enabled native/selected worlds before running the official original runner.
