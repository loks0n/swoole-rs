# Timer queue C ABI gate

`kernel.py` drives the real `swoole-rs-timer` static library through
`native/include/swoole_rs_timer.h` with injected integer timestamps. It does not
sleep, run PHP, read clocks or register reactor events; it is a queue-kernel
test, not a PHP timer test.

```sh
python3 tests/modules/timer/kernel.py --sanitize
```

By default it builds the release archive with Cargo's lockfile. Use
`--no-build --archive /absolute/path/libswoole_rs_timer.a` for a prebuilt
archive, `--output` for the JSON report. `--sanitize` instruments the C/C++
caller with ASan/UBSan, not the Rust archive (see [RUST_ASAN.md](RUST_ASAN.md)).

The header is compiled as C11 with layout static asserts; `kernel.cc` checks
field offsets/widths and runs 13 topic groups with explicit expected statuses,
metadata and event traces. The gate passes only if all 13 pass:

1. Active cancellation keeps the removed view until completion, then returns
   custody once; a second remove is NOT_FOUND.
2. Active updates: a moved one-shot still completes its exact ID; a repeating
   timer updated to the future stays scheduled there.
3. Nested begin/next/end return BUSY while a callback is active.
4. A callback removes B; B's destructor removes C; neither fires.
5. Native equal-deadline witness order A/C/B (no general FIFO promise).
6. Repeat interval coalescing (interval 5 selected at 23 advances to 25, etc.).
7. A callback's later time does not change the selection's captured cutoff.
8. A newly born head updated to an already-due deadline waits for the next round.
9. ID snapshot capacity query/insufficient capacity; destructor-created timers
   survive removal of the captured IDs.
10. Invalid arguments, deadline overflow, rollback time and invalid update are
    atomic; releasing a nonempty or selecting queue returns PENDING.
11. Repeating deadline overflow returns RELEASE_OVERFLOW and the token once.
12. Close during a callback drains other timers and defers the active token.
13. A real single-threaded fork child closes/drains its inherited queue while
    the parent keeps and later fires its own token.

Not exercised (reported in JSON as `not_exercised`): ID, round and execution
counter exhaustion, allocation-fault injection, PHP callbacks/Zend bailout and
reactor wakeups, multithreaded fork allocator safety.
