# Output queues and writes

## Socket output progression

`handle_send`, `handle_sendfile` and `sendfile_async` use one typed Rust
workflow (64 bytes of numeric state) over three pure state machines: DATA
progress, cork/sendfile/completion, and async request publication. Native keeps
Buffer/BufferChunk, SendfileRequest/File and `unique_ptr` storage and performs
sends, file operations, time, errno classification, warnings, allocation,
cork/uncork, publication and pop/destruction after Rust returns.

Requests 16 length, 17 offset, 18 corked, 19 begin, 20 end, 21 timer, 22 buffer
carry fresh observations in original order. DATA offset is re-read after a
partial send; file completion re-reads begin/end after the send/time effects.
Request validation precedes out-buffer presence. A pop is terminal: nothing is
observed after deletion or a callback. The async request stays in its
`unique_ptr` through validation, then publishes the released pointer before the
destructor callback.

`check_sendfile_parameters` (shared by async and sync sendfile) uses
`output_parameters_workflow` on a separate zeroed instance of the same POD:
requests 23 ready, 24 stat-size, 25 published-end. Stat-size is re-read before
published-end, after the Native end write.

The chunk helper uses a signed `off_t` fitting `int64_t`; DATA offset keeps
`uint32_t` wrapping. Signed overflow is not matched.

The M15 sendfile correction applies first when requested; its EINTR early
return and trace prefix stay outside the M05 hunks.

## Writable callback and drain

`Reactor::_writable_callback` and `Reactor::drain_write_buffer` use
`flush_workflow` and `drain_workflow` (4-byte state each; the frozen step APIs
remain). Requests 10..15 read empty, front-kind, close-wait, send-wait, timer and
removed.

- Rust picks DATA (0), SENDFILE (1) or CLOSE (2); other kinds fall back to DATA.
  The front kind is read only when the original loop would.
- Each send result is consumed before requesting `close_wait`, then
  `send_wait`. Once drained, timer deletion precedes a final empty check (asked
  even with no timer) and write-interest removal.
- The originally captured Buffer pointer is kept, not replaced by a fresh
  `socket->out_buffer`.
- Drain: wait returns before the next decision; the writable callback's return
  is ignored; then `close_wait`, then `removed` if needed. Only `wait ==
  SW_ERR` ends that branch.

## Reactor::write_func and _write/_writev

`swr_v1_reactor_write_workflow` owns preparation and fact queries: initial
capacity, conditional default buffer setup, nonblock, conditional fd setup,
admission capacity, Buffer emptiness and conditional TLS/length. The nonempty
path asks for capacity again after `Buffer::length`. Output-pointer, writable
and errno facts are asked only at their original conditional points.

`_write`/`_writev`: Rust rejects SSL before observing any vector (Native emits
the original warning), folds vector lengths with `size_t` wrapping reading only
`iov_len` from real `libc::iovec`, and chooses the post-send append offset
(positive sent offset or zero) and remaining size. Native keeps the
`uint32_t`/`off_t` conversions, pointer arithmetic, send/writev,
`std::function` and Buffer append.

## Typed server Buffer (`SWOOLE_RS_BUFFER_TYPED`)

OFF by default. Socket send/sendfile, reactor writable dispatch,
`BaseFactory::end` and `ReactorThread_onPipeWrite/onWrite` consume the single
typed Rust queue. Rust owns bytes, ordered kind/token custody, current DATA
offset, generation and byte accounting. Native send/sendfile run after copied
front facts return. Partial progress commits against generation and old offset;
pop keeps full queued-byte accounting until detach. Publication stores the
opaque token and disposer together; the Native `unique_ptr` releases custody in
the next pure workflow phase. Sendfile request construction/validation and
disposal stay Native.

The master enqueue hunk is kept separately in
`server-buffer-master-handoff.patch` and is not applied by the reactor overlay.
