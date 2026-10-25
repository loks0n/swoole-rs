# Known bug: idle-retirement event leaked at reactor shutdown

Native Swoole (pinned control and Rust-queue builds alike) can leak one 80-byte
`AsyncEvent` and its 8-byte `std::thread::id` (88 bytes under LSan) allocated in
the idle-retirement branch of `src/os/async_thread.cc` (lines 277-278 at the pin).
It is unrelated to Rust queue storage and to queued ordinary events at shutdown.
It blocks default activation.

Cause (confirmed with test-only scheduling barriers on macOS and Linux, both
engines): the worker's `main_func` creates the retirement event, sets
`release_callback` and the default pipe, sends the pointer and exits. Unlike an
ordinary task, retirement does not add `task_num` credit before publication; its
callback only compensates the completion decrement when the reactor consumes it.
The reactor exits on `task_num == 0`, and the `AsyncThreads` destructor joins
workers and closes the pipe without draining pending pointer messages, so the
retirement callback never runs. Fractional `idle 0.5` truncates to 0 us, which
makes this likely; natural frequency is unmeasured.

A fix needs a native retirement/publication/exit contract: account for pending
retirement notifications before the reactor can exit, keep native thread join/map
authority, and handle failed pipe writes and last-reactor teardown without running
user callbacks after their context is gone. Freeing the opaque tokens in Rust
would break the ownership boundary; adding worker writes to the non-atomic
`task_num` would add a race. No fix is landed.
