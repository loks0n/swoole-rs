# Active-callback fork diagnostics

`fork_active.py` forks a Swoole Process from inside an active timer callback.
It is separate from the original PHPT corpus and changes no `after_fork.phpt`
assertion.

```sh
python3 -m pytest tests/modules/timer/test_fork.py \
  --engine upstream=/absolute/upstream/swoole.so \
  --engine timer=/absolute/timer/swoole.so
```

Each engine/case runs in its own process group with a ten-second limit. Repeat
`--case` to select cases:

- `one-shot`: fork while a one-shot callback is active; the child must print
  `DONE` and exit 0 with no signal; the parent sees one callback, a healthy
  separate timer and no remaining timers.
- `persistent`: fork on the first tick; the child exits cleanly; the parent's
  tick reaches three callbacks, active and sentinel timers cancel, and the timer
  set ends empty.
- `child-reinit`: fork from the first parent tick; inherited IDs must be absent
  in the child, which then creates and clears its own timers (exact child JSON
  is checked). The parent independently reaches three callbacks and count 0.

The child writes its result file only after its assertions run, so a missing
file fails even if the parent exits normally. The explicit child signal/`DONE`
checks caught an earlier adapter bug where `swoole_fork(0)` freed inherited
timers while the copied queue still had an active selection, aborting the child.
Raw fork followed by resuming an inherited selection is not covered.
