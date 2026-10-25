//! Ordinary Socket poll/error/cork policy. Native alone invokes poll, signal
//! dispatch, abort, option syscalls and warnings, after each completed Rust call.
use crate::ReactorOutputAction;
fn out(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
/// Actions:0 return,1 publish normalized timeout,2 poll,3 timeout last-error,
///4 errno EAGAIN,5 errno fact,6 current errno last-error,7 dont_restart fact,
///8 signal dispatch. No revents/pollfd or Native callback enters Rust.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_poll(
    phase: u32,
    result: i32,
    observed: i32,
    timeout: i32,
) -> ReactorOutputAction {
    match phase {
        0 => out(1, 1, if timeout < 0 { -1 } else { timeout.into() }),
        1 | 8 => out(2, 2, 0),
        2 if result == 0 => out(3, 3, 0),
        2 if result < 0 => out(5, 5, 0),
        2 => out(100, 0, 0),
        3 => out(4, 4, 0),
        4 | 6 => out(100, 0, -1),
        5 if observed == libc::EINTR => out(7, 7, 0),
        5 => out(6, 6, 0),
        7 if observed != 0 => out(6, 6, 0),
        7 => out(8, 8, 0),
        _ => out(phase, -1, 0),
    }
}
/// Native return constants/SSL codes are statically asserted by the real caller.
/// Actions:0 return classification,1 Native abort,2 publish kernel_nobufs.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_error(error: i32) -> ReactorOutputAction {
    let (action, value) = if error == libc::EFAULT {
        (1, 4)
    } else if error == libc::EBADF || error == libc::ENOENT {
        (0, 6)
    } else if [
        libc::ECONNRESET,
        libc::ECONNABORTED,
        libc::EPIPE,
        libc::ENOTCONN,
        libc::ETIMEDOUT,
        libc::ECONNREFUSED,
        libc::ENETDOWN,
        libc::ENETUNREACH,
        libc::EHOSTDOWN,
        libc::EHOSTUNREACH,
        1015,
        1017,
    ]
    .contains(&error)
    {
        (0, 3)
    } else if error == 0 || error == libc::EAGAIN || error == libc::EWOULDBLOCK {
        (0, 2)
    } else if error == libc::ENOBUFS {
        (2, 2)
    } else {
        (0, 4)
    };
    out(0, action, value)
}
/// kind0 cork / kind1 uncork, available is target TCP_CORK presence.
/// Actions:0 return,1 nopush fact,2 Native nopush effect,3 nodelay/enable fact,
///4 nopush warning,5 nodelay effect,6 nodelay warning,7 nodelay fact.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_cork(
    kind: u32,
    phase: u32,
    observed: i32,
    available: u32,
) -> ReactorOutputAction {
    let finish = |value| out(100, 0, value);
    let after_nopush = || out(3, 3, 0);
    match (kind, phase) {
        (0 | 1, 0) => out(1, 1, 0),
        (0, 1) if observed != 0 => finish(0),
        (1, 1) if observed == 0 => finish(0),
        (0 | 1, 1) if available != 0 => out(2, 2, if kind == 0 { 1 } else { 0 }),
        (0 | 1, 1) => after_nopush(),
        (0 | 1, 2) if observed < 0 => out(20, 4, 0),
        (0 | 1, 2) => after_nopush(),
        (0, 3) if observed != 0 => out(4, 5, 0),
        (0, 3) => finish(1),
        (0, 4) if observed == 0 => out(5, 6, 0),
        (0, 4 | 5) => finish(1),
        (1, 3) if observed != 0 => out(4, 7, 0),
        (1, 3) => finish(1),
        (1, 4) if observed == 0 => out(5, 5, 1),
        (1, 4) => finish(1),
        (1, 5) if observed == 0 => out(6, 6, 0),
        (1, 5) => finish(1),
        (1, 6) | (0 | 1, 20) => finish(0),
        _ => out(phase, -1, 0),
    }
}
/// kind0 nodelay / kind1 nopush / kind2 fd flags; target availability gates nopush only.
/// Actions:0 return,1 Native option effect,2 Native field publication.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_tcp_option(
    kind: u32,
    phase: u32,
    observed: i32,
    available: u32,
) -> ReactorOutputAction {
    match phase {
        0 if kind == 1 && available == 0 => out(100, 0, -1),
        0 if kind < 3 => out(1, 1, 0),
        1 if kind == 2 && observed == 0 => out(100, 0, 0),
        1 if kind != 2 && observed == -1 => out(100, 0, if kind == 0 { 0 } else { -1 }),
        1 => out(2, 2, 0),
        2 => out(100, 0, if kind == 0 || kind == 2 { 1 } else { 0 }),
        _ => out(phase, -1, 0),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn socket_policy_positive_poll_timeout_normalization() {
        for timeout in [-37, -1, 0, 1, 173] {
            assert_eq!(
                swr_v1_reactor_socket_poll(0, 0, 0, timeout).value,
                if timeout < 0 { -1 } else { timeout as i64 }
            );
            assert_eq!(swr_v1_reactor_socket_poll(1, 0, 0, timeout).action, 2);
            assert_eq!(swr_v1_reactor_socket_poll(2, 1, 0, timeout).value, 0);
        }
    }
    #[test]
    fn socket_policy_positive_cork_eligibility_and_publication() {
        assert_eq!(swr_v1_reactor_socket_cork(0, 1, 1, 1).value, 0);
        assert_eq!(swr_v1_reactor_socket_cork(1, 1, 0, 1).value, 0);
        assert_eq!(swr_v1_reactor_socket_cork(0, 1, 0, 1).value, 1);
        assert_eq!(swr_v1_reactor_socket_cork(1, 1, 1, 1).value, 0);
        assert_eq!(swr_v1_reactor_socket_cork(0, 3, 1, 1).action, 5);
        assert_eq!(swr_v1_reactor_socket_cork(1, 3, 1, 1).action, 7);
        assert_eq!(swr_v1_reactor_socket_cork(1, 4, 0, 1).value, 1);
        for kind in [0, 1] {
            assert_eq!(swr_v1_reactor_socket_tcp_option(kind, 0, 0, 1).action, 1);
            assert_eq!(swr_v1_reactor_socket_tcp_option(kind, 1, 0, 1).action, 2);
        }
        assert_eq!(swr_v1_reactor_socket_error(0).value, 2);
    }
}
