# Output queues and writes

## Socket output progression

`crates/reactor/src/output.rs` runs each operation whole, calling back into
Native through `swr_v1_socket_output_hooks` (send, cork, uncork, send time):

- `handle_send` sends the unsent tail of the front data chunk and classifies the
  result with `catch_error`: pop when it all went, store the advanced offset (and
  `send_wait`) after a short write, `send_wait`/`close_wait` or a warning on
  failure.
- `handle_sendfile` corks once when more than `SW_SOCKET_CORK_MIN_SIZE` remain
  (`sendfile_cork`). Native code then makes the sendfile call and trace, the
  point where the halfclose repair (M15) inserts its EINTR early return when
  selected. `sendfile_sent` classifies the result, records the send time,
  then uncorks and pops once the request is done.
- `sendfile_async` runs the request's construction and range check, the output
  buffer's creation and the enqueue, in that order.

Native code keeps Buffer/BufferChunk, SendfileRequest/File and `unique_ptr`
storage, the sendfile call, warnings, and applies each returned result (pop,
offset, wait flags). `check_sendfile_parameters` uses
`swr_v1_socket_sendfile_range` (fstat included) and the chunk size
`swr_v1_socket_sendfile_chunk`.

## Writable callback

`Reactor::_writable_callback` uses `flush_workflow` (4-byte state);
`drain_write_buffer` is upstream's code. Requests 10..15 read empty, front-kind, close-wait, send-wait, timer and
removed.

- Rust picks DATA (0), SENDFILE (1) or CLOSE (2); other kinds fall back to DATA.
  The front kind is read only when the original loop would.
- Each send result is consumed before requesting `close_wait`, then
  `send_wait`. Once drained, timer deletion precedes a final empty check (asked
  even with no timer) and write-interest removal.
- The originally captured Buffer pointer is kept, not replaced by a fresh
  `socket->out_buffer`.

## Typed server Buffer (`SWOOLE_RS_BUFFER_TYPED`)

On whenever the Rust Buffer and the Rust reactor are both built. Socket send/sendfile, reactor writable dispatch,
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
