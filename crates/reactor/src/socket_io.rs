//! `network::Socket`'s descriptor-level I/O as whole operations, syscall included:
//! `wait_event`'s poll, `clean`, `recvfrom`, `accept` and `connect`. Native code
//! keeps the `Socket` fields, the last-error slot and signal dispatch, which it
//! passes in.
use std::io::Error;
use std::os::raw::{c_int, c_void};

fn errno() -> c_int {
    Error::last_os_error().raw_os_error().unwrap_or(0)
}

/// An I/O outcome: `status` 0 ready, 1 timed out (`wait`) or in progress
/// (`connect`), 2 failed with `error` (an errno).
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SocketIoResult {
    pub status: c_int,
    pub error: c_int,
}

const READY: SocketIoResult = SocketIoResult {
    status: 0,
    error: 0,
};

const fn failed(error: c_int) -> SocketIoResult {
    SocketIoResult { status: 2, error }
}

/// `Socket::wait_event`: poll `fd` for `events` (already translated to poll bits)
/// for `timeout_ms` (negative waits forever). On `EINTR` it fails if
/// `dont_restart`, otherwise calls `dispatch` (`swoole_signal_dispatch`) and polls
/// again.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_socket_wait(
    fd: c_int,
    events: i16,
    timeout_ms: c_int,
    dont_restart: bool,
    dispatch: Option<unsafe extern "C" fn()>,
) -> SocketIoResult {
    let mut event = libc::pollfd {
        fd,
        events,
        revents: 0,
    };
    let timeout = if timeout_ms < 0 { -1 } else { timeout_ms };
    loop {
        // SAFETY: `event` is one local pollfd.
        let ready = unsafe { libc::poll(&raw mut event, 1, timeout) };
        if ready == 0 {
            return SocketIoResult {
                status: 1,
                error: libc::EAGAIN,
            };
        }
        if ready > 0 {
            return READY;
        }
        let error = errno();
        if error != libc::EINTR || dont_restart {
            return failed(error);
        }
        if let Some(dispatch) = dispatch {
            // SAFETY: the native caller passes swoole_signal_dispatch, callable on this thread.
            unsafe { dispatch() };
        }
    }
}

/// `Socket::clean`: discard everything already received, without blocking.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_socket_clean(fd: c_int) {
    let mut buffer = [0_u8; 2048];
    // SAFETY: `buffer` is a local of the length passed.
    while unsafe {
        libc::recv(
            fd,
            buffer.as_mut_ptr().cast::<c_void>(),
            buffer.len(),
            libc::MSG_DONTWAIT,
        )
    } > 0
    {}
}

/// `Socket::recvfrom`: recvfrom(2), retried on `EINTR` up to `retries` times.
///
/// # Safety
/// `buffer` denotes `length` writable bytes; `address` and `address_length` are
/// null or valid for recvfrom(2).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_recvfrom(
    fd: c_int,
    buffer: *mut c_void,
    length: usize,
    flags: c_int,
    address: *mut libc::sockaddr,
    address_length: *mut libc::socklen_t,
    retries: u32,
) -> isize {
    let mut received = 0;
    for _ in 0..retries {
        // SAFETY: the caller lends the buffer and address storage for this call.
        received = unsafe { libc::recvfrom(fd, buffer, length, flags, address, address_length) };
        if received >= 0 || errno() != libc::EINTR {
            break;
        }
    }
    received
}

/// `Socket::accept`'s syscall: the accepted fd, close-on-exec, nonblocking if
/// `nonblock`, or -1. Without accept4 (macOS) it accepts, then sets the options
/// `set_fd_option(nonblock, 1)` sets upstream; `*listener_cloexec` reports that
/// upstream's call there marks the listening socket close-on-exec too.
///
/// # Safety
/// `address` and `address_length` are valid for accept(2); `listener_cloexec`
/// points to a writable bool.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_accept(
    fd: c_int,
    address: *mut libc::sockaddr,
    address_length: *mut libc::socklen_t,
    nonblock: bool,
    listener_cloexec: *mut bool,
) -> c_int {
    #[cfg(target_os = "linux")]
    {
        let _ = listener_cloexec;
        let flags = libc::SOCK_CLOEXEC | if nonblock { libc::SOCK_NONBLOCK } else { 0 };
        // SAFETY: the caller lends the address storage for this call.
        unsafe { libc::accept4(fd, address, address_length, flags) }
    }
    #[cfg(not(target_os = "linux"))]
    {
        // SAFETY: the caller lends the address storage for this call.
        let accepted = unsafe { libc::accept(fd, address, address_length) };
        if accepted >= 0 {
            // Upstream applies set_fd_option to the listening socket here, not the new one.
            let set = crate::swr_v1_socket_fd_option(fd, c_int::from(nonblock), 1).ok;
            // SAFETY: the caller lends a writable bool.
            unsafe { *listener_cloexec = set };
        }
        accepted
    }
}

/// `connect_async`'s loop: connect(2), retried on `EINTR`. Status 1 is
/// `EINPROGRESS` (wait for writability), 2 any other error.
///
/// # Safety
/// `address` denotes `length` readable bytes of a sockaddr.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_connect(
    fd: c_int,
    address: *const libc::sockaddr,
    length: libc::socklen_t,
) -> SocketIoResult {
    loop {
        // SAFETY: the caller lends `length` bytes of sockaddr for this call.
        if unsafe { libc::connect(fd, address, length) } == 0 {
            return READY;
        }
        match errno() {
            libc::EINTR => {}
            libc::EINPROGRESS => {
                return SocketIoResult {
                    status: 1,
                    error: libc::EINPROGRESS,
                };
            }
            error => return failed(error),
        }
    }
}

/// `connect_sync`'s `SO_ERROR` read once the socket is writable: ready, or failed
/// with the pending error (or getsockopt's own errno).
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_socket_pending_error(fd: c_int) -> SocketIoResult {
    let mut pending: c_int = 0;
    // Upstream passes sizeof(len), which equals sizeof(int).
    #[expect(
        clippy::cast_possible_truncation,
        reason = "sizeof(int) fits socklen_t"
    )]
    let mut length = size_of::<libc::socklen_t>() as libc::socklen_t;
    // SAFETY: `pending` and `length` are locals of the sizes passed.
    let read = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            libc::SO_ERROR,
            (&raw mut pending).cast::<c_void>(),
            &raw mut length,
        )
    };
    if read < 0 {
        return failed(errno());
    }
    if pending != 0 {
        return failed(pending);
    }
    READY
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

    fn close(fds: &[c_int]) {
        for &fd in fds {
            // SAFETY: the test opened these descriptors.
            unsafe { libc::close(fd) };
        }
    }

    fn write(fd: c_int, bytes: &[u8]) {
        // SAFETY: `bytes` is readable for its length.
        let written = unsafe { libc::write(fd, bytes.as_ptr().cast::<c_void>(), bytes.len()) };
        assert_eq!(written, bytes.len().cast_signed(), "the whole write");
    }

    #[test]
    fn wait_times_out_then_sees_data() {
        let [a, b] = pair();
        assert_eq!(
            swr_v1_socket_wait(a, libc::POLLIN, 10, false, None),
            SocketIoResult {
                status: 1,
                error: libc::EAGAIN
            }
        );
        write(b, b"x");
        assert_eq!(swr_v1_socket_wait(a, libc::POLLIN, -5, false, None), READY);
        swr_v1_socket_clean(a);
        assert_eq!(
            swr_v1_socket_wait(a, libc::POLLIN, 0, false, None).status,
            1,
            "clean drained it"
        );
        close(&[a, b]);
    }

    #[test]
    fn recvfrom_reads_what_was_sent() {
        let [a, b] = pair();
        write(b, b"hello");
        let mut buffer = [0_u8; 8];
        // SAFETY: `buffer` is a local; no address is requested.
        let n = unsafe {
            swr_v1_socket_recvfrom(
                a,
                buffer.as_mut_ptr().cast(),
                buffer.len(),
                0,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                10,
            )
        };
        assert_eq!(&buffer[..n.cast_unsigned()], b"hello");
        close(&[a, b]);
    }

    #[test]
    fn connect_accept_and_pending_error() {
        // SAFETY: socket(2) has no memory preconditions.
        let listener = unsafe { libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0) };
        let mut address: libc::sockaddr_in = unsafe { std::mem::zeroed() };
        address.sin_family = libc::AF_INET.try_into().unwrap_or_default();
        address.sin_addr.s_addr = u32::from(std::net::Ipv4Addr::LOCALHOST).to_be();
        #[expect(
            clippy::cast_possible_truncation,
            reason = "sizeof(sockaddr_in) fits socklen_t"
        )]
        let mut length = size_of::<libc::sockaddr_in>() as libc::socklen_t;
        let raw = (&raw mut address).cast::<libc::sockaddr>();
        // SAFETY: `address` is a local sockaddr_in of `length` bytes.
        assert_eq!(unsafe { libc::bind(listener, raw, length) }, 0);
        assert!(crate::swr_v1_socket_listen(listener, 0, 8));
        // SAFETY: as above; getsockname fills in the bound port.
        assert_eq!(
            unsafe { libc::getsockname(listener, raw, &raw mut length) },
            0
        );

        // SAFETY: socket(2) has no memory preconditions.
        let client = unsafe { libc::socket(libc::AF_INET, libc::SOCK_STREAM, 0) };
        // SAFETY: as above.
        assert_eq!(unsafe { swr_v1_socket_connect(client, raw, length) }, READY);
        assert_eq!(swr_v1_socket_pending_error(client), READY);

        let mut peer: libc::sockaddr_in = unsafe { std::mem::zeroed() };
        let mut peer_length = length;
        let mut listener_cloexec = false;
        // SAFETY: `peer` is a local sockaddr_in; the flag is a local bool.
        let accepted = unsafe {
            swr_v1_socket_accept(
                listener,
                (&raw mut peer).cast(),
                &raw mut peer_length,
                true,
                &raw mut listener_cloexec,
            )
        };
        assert!(accepted >= 0, "accepted");
        if cfg!(target_os = "linux") {
            // SAFETY: fcntl(F_GETFL) has no memory preconditions.
            assert_ne!(
                unsafe { libc::fcntl(accepted, libc::F_GETFL) } & libc::O_NONBLOCK,
                0,
                "nonblocking"
            );
        }
        close(&[accepted, client, listener]);
        assert_eq!(swr_v1_socket_pending_error(client).status, 2, "closed fd");
    }
}
