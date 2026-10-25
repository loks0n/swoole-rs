# Linux PHP 8.2 repeating-OOM timeout diagnostic

On Linux PHP 8.2, the noncoroutine, uncleared repeating-timer OOM case in
`bailout.py` times out after 5 seconds on both the unchanged original and the
Rust timer: one CALL, one memory fatal, then no SHUTDOWN. That bailout case
remains a failure for both engines.

`oom_observer.py` is a diagnostic, not a gate replacement. It compiles a small
native extension against each engine's headers that registers a reactor end
callback, records timer and PHP executor state, and stops its own event loop
after exactly 8 rounds. It runs `normal` and `oom` modes per engine and exits 0
only if all four processes reach the 8-round budget.

```sh
python3 tests/modules/timer/oom_observer.py \
  --engine upstream=/absolute/original/modules/swoole.so \
  --engine timer=/absolute/candidate/modules/swoole.so \
  --output target/reports/timer-oom-observer.json
```

Linux only, exactly two engines, actual PHP 8.2 runtime and `php-config`.

Observed on both engines: in OOM mode one PHP callback runs while the native
timer keeps advancing (exec_count 0..7, rounds 1..8, timer still registered),
and `delayed_oom` becomes HANDLED (3). The Rust selection is not stalled; the
PHP callable stops running and the binding leaves the repeating timer
registered. PHP 8.2's
[zend_execute_API.c](https://raw.githubusercontent.com/php/php-src/php-8.2.35/Zend/zend_execute_API.c)
returns FAILURE for a callable call after handling delayed OOM; PHP 8.5's
[version](https://raw.githubusercontent.com/php/php-src/php-8.5.11/Zend/zend_execute_API.c)
has no equivalent guard, which matches the version-specific behaviour. Fixing it
belongs to the shared native teardown/event-loop binding.
