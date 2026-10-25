# Captured callback destructor bailout

A successful PHP timer callback can release its captured object while the native
timer node is destroyed. If that object's destructor bails out (e.g. OOM), Zend
escapes from `timer_dtor`, outside the callback bailout catch in
[bailout.md](bailout.md), and native owner teardown aborted on macOS instead of
exiting 255.

The PHP destructor adapter now catches that escape, frees its native Function
container once and records a pending bailout. `release_node` finishes the
detached TimerNode (including the native callback objects), then propagates the
bailout with no live node owner or Rust frame. The abandoned-selection teardown
then closes/completes/drains the queue. The Rust queue and frozen ABI are
unchanged.

`destructor_bailout.py` compares exact exit/stdout/stderr against the first
(control) engine for after/tick x coroutine off/on x destructor
exit/exception/OOM (12 cases per engine, 5-second isolated limits):

```sh
python3 -m pytest tests/modules/timer/test_bailout.py -k test_destructor \
  --engine upstream=/absolute/original/modules/swoole.so \
  --engine timer=/absolute/candidate/modules/swoole.so
```

Modes (mutually exclusive):

- default (`destructor_bailout.php`): destructor runs after a successful
  after/tick callback.
- `--idle-clear` (`destructor_clear.php`): `Timer::clear` and `clearAll`
  outside selection.
- `--event-exit` (`destructor_clear.php`): a callback calls `Event::exit`, which
  runs `php_swoole_timer_clear_all` and destroys another captured timer while
  selection is active.

All three modes pass 24/24 on macOS and Linux. The
`php_swoole_timer_rshutdown` clearAll path (request shutdown) has no dynamic
destructor-fatal gate.
