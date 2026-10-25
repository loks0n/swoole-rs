# Ordinary Socket I/O (`src/network/socket.cc`)

Native keeps bytes, IOVector arrays, Socket/File/SSL objects, errno, syscalls,
callbacks, clocks, counters and logging. Facts are requested in original order
and each effect runs after Rust returns. Public Socket headers, fields, SSL
shutdown/close paths and the M25 address/bind/domain bodies are unchanged.

## recv/send/peek/readv/writev/read_sync/write_sync

One scalar `ordinary_io` plan owns SSL/plain selection, the SSL receive
accumulation loop, errno/restart short circuits, counters/timer decisions,
read-HUP normalization and trace sequencing.

- errno is requested only after a negative result; `dont_restart` only after
  EINTR for send/recv.
- SSL receive observes `nonblock` after publishing each positive accumulation.
- Read classification precedes HUP.
- The vector iterator update precedes the fresh errno read. Vector and peek
  retries keep their unconditional EINTR retry.
- One-shot read/write return READY on a positive partial result; contiguous
  send repeats until the requested length.

Public inline read/write/catch helpers stay Native.

## wait_event, catch_error, cork, options

Rust owns poll result/restart sequencing and timeout normalization, the error
classifier, and cork/option short circuits. Native keeps the `pollfd`, poll
syscall, fresh errno/`dont_restart`, last-error publication, signal dispatch,
abort, `kernel_nobufs`, option syscalls and warnings. `cork` ignores a nodelay
failure after warning; `uncork` returns false after that warning. Only TCP_CORK
availability is a compile-time fact. Nopush's unsupported return and the
setters' `SW_ERR` equality tests are kept. Inline
`catch_write_error/read_error` still forward to `catch_error`.

## fcntl options (`_fcntl_set_option`, `set_fd_option`)

Rust owns GET/SET sequencing, retry, bit transformation and publication using
libc `O_NONBLOCK`/`FD_CLOEXEC`. Status flags finish before descriptor flags.
Each GET and SET retries EINTR. Preserved upstream quirks: a failed GET still
warns and then proceeds to the SET; the GETFD warning says GETFL; negative
arguments skip the fcntl calls but the method still assigns both public
bitfields from the original (possibly negative) arguments.

## Buffer size and timeouts

Rust owns the buffer-size aggregate, the `timeval` helper, set/get/has-timeout
and the kernel-timeout wrappers. Zero timeout is a no-op; fields keep caller
values, including -1. Preserved upstream bug: the read-timeout wrapper calls
`SO_SNDTIMEO` and publishes `write_timeout`; the write-timeout wrapper calls
`SO_RCVTIMEO` and publishes `read_timeout`. Seconds truncate through C `int`;
microseconds keep the two left-associated multiplications after subtracting
seconds. NaN/out-of-range conversion is undefined in C and not matched. The
typed timeout reply is 20 bytes.

## Forwarding, liveness, drain

Rust selects sendfile SSL/plain, async send availability/fallback, liveness
classification and clean/drain iteration. Sendfile returns the effect result
directly (no retry), below the M15 EINTR prefix. Clean keeps its 2048-byte
buffer and `MSG_DONTWAIT`, repeating only after a positive result. Liveness
resets errno before its one-byte peek, classifies only negative results and keeps
the CLOSE (`SW_CLOSE` = 3) versus other decision.

## Datagrams

`sendto_sync` and sockaddr `recvfrom_sync` use the blocking plan (kind 6). A
short positive datagram completes one message. `recvfrom` uses the ordinary-I/O
plan (kind 9): errno only on a negative result, EINTR repeats up to
`SW_SOCKET_RETRY_COUNT`. The Address overload is byte-identical Native
marshalling onto the sockaddr overload.

## connect_async / connect_sync

One operation/phase function, using the existing output POD:

- Async sets nonblock (return ignored), calls `connect(Address)`, reads errno
  only after a negative result. EINTR retries. Other negatives publish errno,
  then re-read errno after that publication to choose WAIT or ERROR. Success
  returns READY.
- Sync calls async. READY maps to OK with no timeout read or blocking restore.
  WAIT reads `connect_timeout` once; Native keeps `sec2msec(double)` and the
  original long→double→int conversions.
- Negative wait publishes ETIMEDOUT and returns ERR. Otherwise Native calls
  `getsockopt(SO_ERROR)` with `socklen_t len=sizeof(len)`; a negative result
  publishes fresh errno, a nonzero output publishes that error, both return
  ERR. Only zero restores blocking mode (bool ignored) and returns OK.

## Blocking calls

`wait_for`, `what_event_want`, `send_sync`, `writev_sync`, `sendfile_sync`,
`recv_sync` and `IOVector::update_iterator` use transient POD state. Rust owns
wait preparation, callback-result routing, kernel-nobufs continuation, timeout
arithmetic and the final outcome. SSL presence is queried before want-write, then
want-read only if needed. The cumulative elapsed-time subtraction and C long
conversion order are unchanged. `writev_sync` returns a positive partial write
immediately. Sync sendfile keeps validation, range/cork, wait, uncork and File
cleanup order. A template carries Native send effects between decisions; it
owns no payload.

`recv_sync` (kind 5): Rust gives the remaining span and clears `MSG_WAITALL`
before each recv. Without WAITALL one positive partial receive returns;
with WAITALL it repeats to the requested length.

## IOVector

Default: Native constructor, two arrays, copies and destructor. Rust scans
`iovec` lengths lazily (never payloads) and returns remaining/index/offset and
pointer progress; Native writes the public fields. Full completion publishes
counters and returns before touching the iterator. The upstream `offset_bytes`
quirk at an exact segment boundary after partial progress is kept.

`SWOOLE_RS_REACTOR_IOV_OWNED` = 1 (requires `SWOOLE_RS_REACTOR`): the
constructor makes one Rust allocation holding release `Layout` metadata followed
by two contiguous `iovec` spans (original and iterator), copied from the caller's
descriptors. Payload bytes are not copied or owned. Native publishes the
returned pointers/counts; allocation refusal returns before Native throws
`bad_array_new_length` or `bad_alloc`. Release uses the allocation-local Layout,
not the public count, and never drops payloads; NULL release is a no-op. Inline
`length` reads the original span each call with C `size_t` wrapping. Public class
layout and getters are unchanged.

Incompatible under ON: replacing the public pointers with Native `new[]`
arrays, or calling `delete[]` on Rust spans. Implicit C++ shallow copy is
unchanged.
