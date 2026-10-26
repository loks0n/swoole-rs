//! Whole ordinary Socket syscall selection, receive accumulation, retry and
//! publication policy. Native owns all bytes, descriptors, errno, SSL and clocks.
use crate::ReactorOutputAction;
fn out(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
fn after(kind: u32, result: isize) -> ReactorOutputAction {
    if kind == 2 {
        out(9, 12, 0)
    } else {
        out(100, 0, result as i64)
    }
}
fn retry(kind: u32, result: isize) -> ReactorOutputAction {
    if result < 0 {
        out(3, 4, 0)
    } else {
        after(kind, result)
    }
}
/// Kinds (0 send and 1 recv are upstream's inline code again, #366): 2 peek,3 readv,4 writev,5 sendfile,6 async,7 clean,8 liveness,9 bounded datagram receive.
/// Actions:0 return,
///1 observe SSL,2 SSL effect,3 plain effect,4 errno,5 dont_restart,
///6 publish positive counter,7 observe timer,8 publish clock,9 classify read,
///10 observe HUP,11 publish zero,12 trace,13 observe nonblock,
///15 publish receive total,16 add receive result,17 publish peek flags,
///18 event-availability fact,19 sync send,20 event write,21 clean recv,
///22 reset errno,23 liveness peek,24 datagram receive (value=attempt ordinal).
/// Only requested facts are observed. No pointer/reference or Native owner enters.
#[unsafe(no_mangle)]
#[expect(
    clippy::cast_sign_loss,
    reason = "native ssize_t results compared as size_t"
)]
pub extern "C" fn swr_v1_reactor_ordinary_io(
    kind: u32,
    phase: u32,
    observed: i32,
    result: isize,
    total: isize,
    length: usize,
    flags: i32,
) -> ReactorOutputAction {
    if !(2..=9).contains(&kind) {
        return out(phase, -1, 0);
    }
    match phase {
        0 if kind == 9 && length == 0 => out(100, 0, 0),
        0 if kind == 9 => out(50, 24, 0),
        50 if kind == 9 && result < 0 => out(51, 4, 0),
        50 if kind == 9 => out(100, 0, result as i64),
        51 if kind == 9 && observed == libc::EINTR && (total as usize) + 1 < length => {
            out(50, 24, (total + 1) as i64)
        }
        51 if kind == 9 => out(100, 0, result as i64),
        0 if kind == 8 => out(42, 22, 0),
        42 if kind == 8 => out(43, 23, 0),
        43 if kind == 8 && result < 0 => out(44, 9, 0),
        43 if kind == 8 => out(100, 0, (result != 0).into()),
        44 if kind == 8 => out(100, 0, (observed != 3).into()),
        0 if kind == 7 => out(2, 21, 0),
        0 if kind == 6 => out(41, 18, 0),
        41 if kind == 6 => out(2, if observed == 0 { 19 } else { 20 }, 0),
        2 if kind == 7 => {
            if result > 0 {
                out(2, 21, 0)
            } else {
                out(100, 0, 0)
            }
        }
        2 if kind == 5 || kind == 6 => out(100, 0, result as i64),
        0 if kind == 2 => out(40, 17, (flags | libc::MSG_PEEK).into()),
        0 | 40 => out(1, 1, 0),
        1 => out(2, if observed != 0 { 2 } else { 3 }, 0),
        2 => retry(kind, result),
        3 if observed == libc::EINTR => out(1, 1, 0),
        3 => after(kind, result),
        4 if observed == 0 => out(1, 1, 0),
        4 => after(kind, result),
        9 => out(100, 0, result as i64),
        _ => out(phase, -1, 0),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn datagram_positive_receive_returns_without_extra_observations() {
        for result in [1, 3, 17] {
            let call = swr_v1_reactor_ordinary_io(9, 0, 0, 0, 0, 10, 0);
            assert_eq!((call.action, call.value), (24, 0));
            let done = swr_v1_reactor_ordinary_io(9, call.phase, 0, result, 0, 10, 0);
            assert_eq!((done.action, done.value), (0, result as i64));
        }
    }
    #[test]
    fn vector_and_peek_do_not_publish_socket_counters() {
        for kind in [2, 3, 4] {
            let reply = swr_v1_reactor_ordinary_io(kind, 2, 0, 7, 0, 12, 0);
            assert_eq!(reply.action, if kind == 2 { 12 } else { 0 });
            assert_eq!(swr_v1_reactor_ordinary_io(kind, 9, 0, 7, 0, 12, 0).value, 7);
        }
        assert_eq!(
            swr_v1_reactor_ordinary_io(2, 0, 0, 0, 0, 12, 8).value,
            (8 | libc::MSG_PEEK) as i64
        );
    }
    #[test]
    fn forwarding_and_clean_value_policy() {
        assert_eq!(swr_v1_reactor_ordinary_io(8, 0, 0, 0, 0, 0, 0).action, 22);
        assert_eq!(swr_v1_reactor_ordinary_io(8, 42, 0, 0, 0, 0, 0).action, 23);
        assert_eq!(swr_v1_reactor_ordinary_io(8, 43, 0, 1, 0, 0, 0).value, 1);
        assert_eq!(swr_v1_reactor_ordinary_io(5, 0, 0, 0, 0, 1, 0).action, 1);
        for tls in [0, 1] {
            assert_eq!(
                swr_v1_reactor_ordinary_io(5, 1, tls, 0, 0, 1, 0).action,
                if tls == 0 { 3 } else { 2 }
            );
        }
        assert_eq!(swr_v1_reactor_ordinary_io(5, 2, 0, 7, 0, 1, 0).value, 7);
        assert_eq!(swr_v1_reactor_ordinary_io(6, 0, 0, 0, 0, 1, 0).action, 18);
        for active in [0, 1] {
            assert_eq!(
                swr_v1_reactor_ordinary_io(6, 41, active, 0, 0, 1, 0).action,
                if active == 0 { 19 } else { 20 }
            );
        }
        assert_eq!(swr_v1_reactor_ordinary_io(6, 2, 0, 7, 0, 1, 0).value, 7);
        assert_eq!(swr_v1_reactor_ordinary_io(7, 0, 0, 0, 0, 0, 0).action, 21);
        assert_eq!(swr_v1_reactor_ordinary_io(7, 2, 0, 7, 0, 0, 0).action, 21);
        assert_eq!(swr_v1_reactor_ordinary_io(7, 2, 0, 0, 0, 0, 0).action, 0);
    }
}
