//! `network::Socket`'s per-request reads and writes as whole operations, syscall
//! included: `recv`, `send` and `peek` with their EINTR and `dont_restart` rules,
//! and `catch_error`'s errno classification. A TLS socket passes its OpenSSL call
//! (`ssl_recv`, `ssl_send`, `SSL_peek`), which this loop drives. Native code keeps
//! the byte counters, timers and trace.
use std::io::Error;
use std::os::raw::{c_int, c_void};

/// A TLS read or write on `socket`: what `ssl_recv`/`ssl_send`/`SSL_peek` return.
pub type TlsIo =
    unsafe extern "C" fn(socket: *mut c_void, buffer: *mut c_void, length: usize) -> isize;

fn interrupted() -> bool {
    Error::last_os_error().raw_os_error() == Some(libc::EINTR)
}

/// `Socket::recv`: recv(2), or `tls` reads until `length` bytes when the socket is
/// nonblocking or `MSG_WAITALL` is set. Retried on EINTR unless `dont_restart`;
/// errno is left as the last call set it.
///
/// # Safety
/// `buffer` denotes `length` writable bytes; `tls`, when given, is valid for `socket`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_recv(
    fd: c_int,
    buffer: *mut c_void,
    length: usize,
    flags: c_int,
    nonblock: bool,
    dont_restart: bool,
    tls: Option<TlsIo>,
    socket: *mut c_void,
) -> isize {
    loop {
        let total = match tls {
            Some(read) => {
                let mut total: isize = 0;
                while total.cast_unsigned() < length {
                    // SAFETY: `total < length`, so the rest of the caller's buffer starts in bounds.
                    let rest = unsafe { buffer.cast::<u8>().add(total.cast_unsigned()) };
                    // SAFETY: the caller's TLS read for this socket, into the rest of its buffer.
                    let read = unsafe { read(socket, rest.cast(), length - total.cast_unsigned()) };
                    if read <= 0 {
                        if total == 0 {
                            total = read;
                        }
                        break;
                    }
                    total += read;
                    if !(nonblock || flags & libc::MSG_WAITALL != 0) {
                        break;
                    }
                }
                total
            }
            // SAFETY: the caller lends `length` writable bytes.
            None => unsafe { libc::recv(fd, buffer, length, flags) },
        };
        if !(total < 0 && interrupted() && !dont_restart) {
            return total;
        }
    }
}

/// `Socket::send`: send(2) or one `tls` write, retried on EINTR unless `dont_restart`.
///
/// # Safety
/// `buffer` denotes `length` readable bytes; `tls`, when given, is valid for `socket`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_send(
    fd: c_int,
    buffer: *const c_void,
    length: usize,
    flags: c_int,
    dont_restart: bool,
    tls: Option<TlsIo>,
    socket: *mut c_void,
) -> isize {
    loop {
        let sent = match tls {
            // SAFETY: the caller's TLS write for this socket; it only reads the buffer.
            Some(write) => unsafe { write(socket, buffer.cast_mut(), length) },
            // SAFETY: the caller lends `length` readable bytes.
            None => unsafe { libc::send(fd, buffer, length, flags) },
        };
        if !(sent < 0 && interrupted() && !dont_restart) {
            return sent;
        }
    }
}

/// `Socket::peek`: recv(2) with `MSG_PEEK`, or `tls` (`SSL_peek`), retried on EINTR.
///
/// # Safety
/// `buffer` denotes `length` writable bytes; `tls`, when given, is valid for `socket`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_peek(
    fd: c_int,
    buffer: *mut c_void,
    length: usize,
    flags: c_int,
    tls: Option<TlsIo>,
    socket: *mut c_void,
) -> isize {
    loop {
        let peeked = match tls {
            // SAFETY: the caller's SSL_peek for this socket, into its buffer.
            Some(peek) => unsafe { peek(socket, buffer, length) },
            // SAFETY: the caller lends `length` writable bytes.
            None => unsafe { libc::recv(fd, buffer, length, flags | libc::MSG_PEEK) },
        };
        if !(peeked < 0 && interrupted()) {
            return peeked;
        }
    }
}

/// `SW_ERROR_SSL_BAD_CLIENT` and `SW_ERROR_SSL_RESET` (native asserts them).
const SSL_BAD_CLIENT: c_int = 1015;
const SSL_RESET: c_int = 1017;
/// `swReturnCode`.
const WAIT: c_int = 2;
const CLOSE: c_int = 3;
const ERROR: c_int = 4;
const INVALID: c_int = 6;

/// `Socket::catch_error`: what an errno (or Swoole TLS error) means for the socket.
/// `ENOBUFS` waits and sets `*kernel_nobufs`; `EFAULT` aborts, as upstream does.
///
/// # Safety
/// `kernel_nobufs` points to a writable bool.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_catch_error(
    error: c_int,
    kernel_nobufs: *mut bool,
) -> c_int {
    #[expect(
        unreachable_patterns,
        reason = "EWOULDBLOCK equals EAGAIN on these platforms"
    )]
    match error {
        libc::EFAULT => std::process::abort(),
        libc::EBADF | libc::ENOENT => INVALID,
        libc::ECONNRESET
        | libc::ECONNABORTED
        | libc::EPIPE
        | libc::ENOTCONN
        | libc::ETIMEDOUT
        | libc::ECONNREFUSED
        | libc::ENETDOWN
        | libc::ENETUNREACH
        | libc::EHOSTDOWN
        | libc::EHOSTUNREACH
        | SSL_BAD_CLIENT
        | SSL_RESET => CLOSE,
        libc::EAGAIN | libc::EWOULDBLOCK | 0 => WAIT,
        libc::ENOBUFS => {
            // SAFETY: the caller lends a writable bool.
            unsafe { *kernel_nobufs = true };
            WAIT
        }
        _ => ERROR,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair() -> [c_int; 2] {
        let mut fds = [0; 2];
        // SAFETY: `fds` holds the two descriptors socketpair writes.
        assert_eq!(
            unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_STREAM, 0, fds.as_mut_ptr()) },
            0
        );
        fds
    }

    unsafe extern "C" fn tls_in_pieces(
        socket: *mut c_void,
        buffer: *mut c_void,
        length: usize,
    ) -> isize {
        // The "TLS" layer hands out two bytes per call from a counter.
        let left = unsafe { &mut *socket.cast::<usize>() };
        if *left == 0 {
            return 0;
        }
        let n = length.min(2).min(*left);
        unsafe { std::ptr::write_bytes(buffer.cast::<u8>(), b'x', n) };
        *left -= n;
        n.cast_signed()
    }

    #[test]
    fn plain_send_recv_and_peek() {
        let [a, b] = pair();
        let null = std::ptr::null_mut();
        // SAFETY: local buffers, no TLS.
        unsafe {
            assert_eq!(
                swr_v1_socket_send(b, b"hello".as_ptr().cast(), 5, 0, false, None, null),
                5
            );
            let mut buffer = [0_u8; 8];
            assert_eq!(
                swr_v1_socket_peek(a, buffer.as_mut_ptr().cast(), 8, 0, None, null),
                5
            );
            assert_eq!(
                swr_v1_socket_recv(
                    a,
                    buffer.as_mut_ptr().cast(),
                    8,
                    0,
                    false,
                    false,
                    None,
                    null
                ),
                5
            );
            assert_eq!(&buffer[..5], b"hello");
            libc::close(a);
            libc::close(b);
        }
    }

    #[test]
    fn tls_reads_accumulate_only_when_nonblocking_or_waitall() {
        let mut buffer = [0_u8; 8];
        let mut left: usize = 7;
        let socket = (&raw mut left).cast::<c_void>();
        // SAFETY: local buffer and counter; the stub reads within them.
        unsafe {
            assert_eq!(
                swr_v1_socket_recv(
                    -1,
                    buffer.as_mut_ptr().cast(),
                    8,
                    0,
                    false,
                    false,
                    Some(tls_in_pieces),
                    socket
                ),
                2
            );
            assert_eq!(
                swr_v1_socket_recv(
                    -1,
                    buffer.as_mut_ptr().cast(),
                    8,
                    0,
                    true,
                    false,
                    Some(tls_in_pieces),
                    socket
                ),
                5
            );
            assert_eq!(
                swr_v1_socket_recv(
                    -1,
                    buffer.as_mut_ptr().cast(),
                    8,
                    0,
                    true,
                    false,
                    Some(tls_in_pieces),
                    socket
                ),
                0
            );
        }
    }

    #[test]
    fn errors_classify_as_upstream() {
        let mut nobufs = false;
        // SAFETY: `nobufs` is a local.
        let mut classify = |error| unsafe { swr_v1_socket_catch_error(error, &raw mut nobufs) };
        assert_eq!(classify(libc::EAGAIN), WAIT);
        assert_eq!(classify(0), WAIT);
        assert_eq!(classify(libc::EPIPE), CLOSE);
        assert_eq!(classify(SSL_RESET), CLOSE);
        assert_eq!(classify(libc::EBADF), INVALID);
        assert_eq!(classify(libc::EINVAL), ERROR);
        assert_eq!(classify(libc::ENOBUFS), WAIT);
        assert!(nobufs, "ENOBUFS records kernel_nobufs");
    }
}
