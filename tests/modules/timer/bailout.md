# PHP timer callback bailout

Zend bailouts (exit, uncaught exception, fatal OOM) from a PHP timer callback
used to skip native selection completion, leaving the Rust selection active;
native owner destruction then aborted the process (SIGABRT instead of exit 255).

## Native repair

The PHP timer callback catches the Zend bailout only to mark its native
selection abandoned, restores Zend's previous bailout target and reissues
`zend_bailout`. No Rust code, callback, allocator or destructor runs inside the
catch. The native owner destructor treats that terminal state like an inherited
child selection: close, complete the active ID, end selection, release the
token, drain and release the queue. The frozen Rust ABI is unchanged. Deleting
the owner while a callback will resume remains forbidden.

Cleanup is deferred until owner destruction so PHP shutdown functions still see
the same timer count, removed flag, repeat count, round and discoverability as
upstream. The fixture compares those fields, excluding only `exec_msec`.

## Gate

`bailout.py` runs 16 cases per engine: after/tick x coroutine off/on x
self-cleared exit/exception/OOM plus uncleared OOM. Each process has a 5-second
isolated process-group limit. Exit code, stdout and stderr must equal the first
(control) engine's exactly.

```sh
python3 -m pytest tests/modules/timer/test_bailout.py -k test_callback \
  --engine upstream=/absolute/clean/original/modules/swoole.so \
  --engine timer=/absolute/immutable/timer/modules/swoole.so
```

`test_control_timeout.py` covers the driver's classification without PHP.

## Known failures

- macOS PHP 8.5: 32/32 pass.
- Linux PHP 8.2: 30 cases match; the noncoroutine uncleared repeating OOM case
  times out on both original and candidate, so the gate fails. See
  [oom_observer.md](oom_observer.md).

Captured-object destructor bailouts are covered by
[destructor_bailout.md](destructor_bailout.md).
