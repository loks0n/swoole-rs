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

## File

- `swr_v1_os_fs_error`: result 0 = stop; native-provided transient-errno flag =
  retry; otherwise warn.
- `swr_v1_os_content`: classifies empty, then too-large. Native size errors,
  allocation, logging and partial-positive write truthiness are unchanged.
- `swr_v1_os_file_io_next`: sequences `File::read_all` and `File::write_all`. A
  zeroed, exclusive caller-stack cursor holds completed bytes and phase; native
  fixes the requested length between calls. Action 1 = do native IO, 2 = original
  warning then partial return, 0 = return the accumulated count. Positive results
  advance with `size_t` arithmetic, zero stops, negative transient results retry
  at the same offset, other errors warn once then stop. Each write attempt rechecks
  APPEND: write uses the file offset; `pwrite`/`pread` use the accumulated count.
  A positive partial count stays truthy in `file_put_contents`.
- `swr_v1_os_line_end` (frozen): accepts an initialized prefix with
  length <= `isize::MAX` and a readable pointer, or zero length. Returns the
  terminator-inclusive length for NUL/newline, otherwise 0.
- `swr_v1_os_file_line_result` (`File::read_line`): for read results <= 0 returns
  the result without touching data, writing NUL or seeking. For a positive prefix
  the first NUL/newline is included; no terminator selects the whole read length
  plus the original extra seek byte. Returns a 16-byte LP64 value: signed length,
  then two `u32` (action, extra). Native captures `get_offset` before
  `read(_n-1)`, writes NUL before `set_offset`, ignores the seek return, and
  computes offset + signed length + signed extra left to right (do not precompute
  length+1 or promote offsets to unsigned). Invalid `_n == 0`/buffer bounds are
  not defined inputs.
- `swr_v1_os_file_content_next` (`file_get_contents`): exclusive zeroed stack
  state with phase and positive signed size. Selects native stat, a lazy max-size
  read of `SwooleG.max_file_content` (positive sizes only), the original
  open/empty/large diagnostics and null returns, or native
  allocation/read/finalization. Negative sizes return without another log; zero
  logs. Native does `make_shared<String>(filesize+1)`, `read_all`, length then NUL.
  Partial/zero reads still yield non-null content.
- `swr_v1_os_read_content_next` (`File::read_content`): stack `u32` phase only.
  Native `n=0` and `make_shared<String>(SW_BUFFER_SIZE_STD)` precede the first
  call. Action 1 reads; positive results select action 2 (`String::grow(n)` then
  a fresh read); non-positive results return the accumulated String (no NUL,
  warning, EINTR retry or empty-null change). Native recomputes `str+length` and
  `capacity-length` after growth. Malformed state is rejected.

## SysV message queue

`swr_v1_os_permissions`, `swr_v1_os_queue_flags`, `swr_v1_os_queue_error`: default 0666 for values outside
(0, 01000); blocking mutates flags only; push retries EINTR before EAGAIN. Pop
does not retry. SysV resource ownership stays native. Module tests never use
upstream's fixed SysV key or mutate host IPC resources.

## Random bytes and sendfile

- `swr_v1_os_random_bytes_next` owns the outer `swoole_random_bytes` loop in
  `src/os/base.cc`. Stack cursor: completed `size_t` count and phase. Only result
  -1 consults the native EINTR/EAGAIN flag (transient retries at the same prefix;
  other -1 returns partial progress). Other results use unsigned `size_t`
  addition. A zero result repeats without progress and without a retry limit, so a
  permanently zero backend never terminates, as in upstream. Empty size returns
  before the first backend call. Do not apply File IO's zero-stop policy here.
  `swr_v1_os_random_error` remains ABI-compatible. `src/core/base.cc::swoole_system_random`
  is not touched.
- `swr_v1_os_sendfile_action`: syscall, bytes and offset updates stay native. On
  Darwin/BSD the offset update happens before the action. Linux uses its direct
  `sendfile` syscall.
- `swr_v1_os_sendfile_fallback_next` (`!HAVE_SENDFILE`): stack cursor. Bounds the
  single read by native buffer capacity, writes once only after a positive read,
  maps zero/negative reads to the native warning plus pinned `SW_ERR`, preserves
  the exact write return, and requests offset publication for every non-negative
  write including zero. No retries, including EINTR/EAGAIN. Native keeps the
  bytes, both syscalls, warning/errno and `*offset += result`.

Still native: OS base lifecycle, entropy backends, resolver, File storage and
UnixSocket construction.
