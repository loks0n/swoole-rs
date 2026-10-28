# OS support policy v1

Opt-in feature bit 131072 (`ossupport`). ABI: `docs/os-support-abi-v1.md` and
`swoole_rs_ossupport.h`. Patched upstream files: `src/os/async_thread.cc`,
`src/os/file.cc`, `src/os/msg_queue.cc`, `src/os/base.cc`, `src/os/sendfile.cc`.

Rust owns the async thread pool. File, SysV queue, sendfile and entropy code is
still policy only: Rust keeps no state there and every native effect runs after
Rust returns.

## Thread pool

`crates/ossupport/src/pool.rs` is upstream's `async::ThreadPool`: one process-wide
pool (created on first `swr_v1_os_pool_acquire` with that call's configuration,
restarted after a full shutdown), its queue, `std::thread` workers, growth
scheduling and idle retirement. Each `AsyncThreads` holds one reference; the last
release shuts the pool down and joins every worker, as upstream's `use_count() == 1`.

Event tokens are native `AsyncEvent` pointers that Rust never dereferences. Native
hooks (`swr_v1_os_pool_hooks`) run on worker threads: `execute` runs the handler
(missing handler wins over canceled) and writes the event to its pipe; `retire`
sends the idle worker's key to the default pipe, whose callback joins it with
`swr_v1_os_pool_join`. Defaults, scheduling and the whole-second idle wait match
upstream v6.2.4. Workers get an 8 MiB stack. Known remaining issues: the
unsynchronized `canceled` field and the retirement leak in
[retirement-shutdown-gap.md](retirement-shutdown-gap.md).

## File, sendfile and entropy

`crates/ossupport/src/file.rs` runs the syscalls; native keeps the descriptors,
`String` allocation and logging. Each call returns right after a failing syscall
so the native `swoole_sys_warning` sees its errno.

- `swr_v1_os_file_write_all` / `read_all` (`File::write_all` / `read_all`):
  `write` in append mode, otherwise `pwrite`/`pread` at the progress; zero stops,
  `EINTR`/`EAGAIN` retry, other errors set `failed` for the upstream warning.
- `swr_v1_os_file_read_line`: reads `n - 1` bytes, keeps the first NUL/newline,
  NUL-terminates and seeks past the line; without one it seeks one byte past the
  data read, as upstream.
- `swr_v1_os_file_size`: `fstat` errno or `EISDIR` for non-regular files.
- `swr_v1_os_sendfile` (Darwin, FreeBSD): retries `EINTR`, advancing the offset by
  each call's progress; Darwin retries with the length the interrupted call
  reported. `swr_v1_os_sendfile_copy` (`!HAVE_SENDFILE`): one 64 KiB `pread` and
  one `write`, no retries. Linux keeps its direct `sendfile`.
- `swr_v1_os_random_bytes`: `getrandom` on Linux/Android (retrying `EINTR`/`EAGAIN`,
  a zero result repeats), `arc4random_buf` elsewhere.

`file_get_contents`, `file_put_contents` and `File::read_content` stay native:
they compose the calls above with `String` and the upstream logs.

## SysV message queue

`swr_v1_os_permissions`, `swr_v1_os_queue_flags`, `swr_v1_os_queue_error`: default 0666 for values outside
(0, 01000); blocking mutates flags only; push retries EINTR before EAGAIN. Pop
does not retry. SysV resource ownership stays native. Module tests never use
upstream's fixed SysV key or mutate host IPC resources.

Still native: OS base lifecycle, resolver, File storage and UnixSocket
construction.
