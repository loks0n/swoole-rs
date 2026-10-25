//! Whole ordinary Socket buffer and timeout facade policy. Native owns option
//! calls, fields, errno, warnings and public timeval representation.
use crate::ReactorOutputAction;
fn out(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
/// kind0 aggregate /1 recv /2 send. Actions:0 return,1 send-buffer method,
///2 recv-buffer method,3 actual option. Retain && short circuit and ==0 test.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_buffers(
    kind: u32,
    phase: u32,
    observed: i32,
) -> ReactorOutputAction {
    match (kind, phase) {
        (0, 0) => out(1, 1, 0),
        (0, 1) if observed != 0 => out(2, 2, 0),
        (0, 1 | 2) => out(100, 0, (observed != 0).into()),
        (1 | 2, 0) => out(3, 3, 0),
        (1 | 2, 3) => out(100, 0, (observed == 0).into()),
        _ => out(phase, -1, 0),
    }
}
#[repr(C)]
pub struct ReactorSocketTimeoutReply {
    pub phase: u32,
    pub action: i32,
    pub value: i32,
    pub seconds: i32,
    pub microseconds: i32,
}
fn timeout(phase: u32, action: i32, value: i32) -> ReactorSocketTimeoutReply {
    ReactorSocketTimeoutReply {
        phase,
        action,
        value,
        seconds: 0,
        microseconds: 0,
    }
}
fn publish_timeout(phase: u32, kind: i32) -> ReactorSocketTimeoutReply {
    for index in phase..4 {
        if kind & (1 << index) != 0 {
            return timeout(index + 1, 3, index as i32 + 1);
        }
    }
    timeout(100, 0, 0)
}
/// kind0 timeval option helper /1 set-timeouts /2 get-timeout /3 has-timedout
/// /4 kernel wrapper. Actions:0 return(value or chosen field),1 Native timeval
/// publication+setsockopt,2 original warning,3 field publication,4 errno fact,
///5 last-error fact,6 invalid-type assertion,7 Native helper call.
/// Floating conversion matches pinned C int casts only in their defined finite
/// representable domain. NaN/out-of-range conversion parity is not asserted.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_timeout(
    operation: u32,
    phase: u32,
    observed: i32,
    kind: i32,
    value: f64,
) -> ReactorSocketTimeoutReply {
    match (operation, phase) {
        (0, 0) => {
            let seconds = value as i32;
            let microseconds = ((value - seconds as f64) * 1000.0 * 1000.0) as i32;
            ReactorSocketTimeoutReply {
                phase: 1,
                action: 1,
                value: 0,
                seconds,
                microseconds,
            }
        }
        (0, 1) if observed < 0 => timeout(2, if kind == libc::SO_SNDTIMEO { 2 } else { 8 }, 0),
        (0, 1) => timeout(100, 0, 1),
        (0, 2) => timeout(100, 0, 0),
        (1, 0) if value == 0.0 => timeout(100, 0, 0),
        (1, 0..=4) => publish_timeout(phase, kind),
        (2, 0) => match kind {
            1 => timeout(100, 0, 1),
            2 => timeout(100, 0, 2),
            4 => timeout(100, 0, 3),
            8 => timeout(100, 0, 4),
            _ => timeout(100, 6, 0),
        },
        (3, 0) => timeout(1, 4, 0),
        (3, 1) if observed == libc::EAGAIN => timeout(100, 0, 1),
        (3, 1) => timeout(2, 4, 0),
        (3, 2) if observed == libc::ETIMEDOUT => timeout(100, 0, 1),
        (3, 2) => timeout(3, 5, 0),
        (3, 3) => timeout(100, 0, (observed == 6002).into()),
        (4, 0) => timeout(1, 7, 0),
        (4, 1) if observed != 0 => timeout(2, 3, 0),
        (4, 1) => timeout(100, 0, 0),
        (4, 2) => timeout(100, 0, 1),
        _ => timeout(phase, -1, 0),
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_timeout_layout(field: u32) -> usize {
    match field {
        0 => std::mem::size_of::<ReactorSocketTimeoutReply>(),
        1 => std::mem::align_of::<ReactorSocketTimeoutReply>(),
        2 => std::mem::offset_of!(ReactorSocketTimeoutReply, phase),
        3 => std::mem::offset_of!(ReactorSocketTimeoutReply, action),
        4 => std::mem::offset_of!(ReactorSocketTimeoutReply, value),
        5 => std::mem::offset_of!(ReactorSocketTimeoutReply, seconds),
        6 => std::mem::offset_of!(ReactorSocketTimeoutReply, microseconds),
        _ => usize::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn socket_options_positive_timeout_order_and_conversion() {
        for kind in 0..16 {
            let mut phase = 0;
            let mut got = Vec::new();
            loop {
                let r = swr_v1_reactor_socket_timeout(1, phase, 0, kind, 1.25);
                if r.action == 0 {
                    break;
                }
                assert_eq!(r.action, 3);
                got.push(r.value);
                phase = r.phase;
            }
            let expected: Vec<_> = (0..4)
                .filter(|i| kind & (1 << i) != 0)
                .map(|i| i + 1)
                .collect();
            assert_eq!(got, expected);
        }
        assert_eq!(swr_v1_reactor_socket_timeout(1, 0, 0, 15, 0.0).action, 0);
        for (value, seconds, micros) in [(0.125, 0, 125000), (1.25, 1, 250000), (7.75, 7, 750000)] {
            let r = swr_v1_reactor_socket_timeout(0, 0, 0, 0, value);
            assert_eq!((r.seconds, r.microseconds), (seconds, micros));
        }
    }
    #[test]
    fn socket_options_positive_buffer_and_kernel_publication() {
        assert_eq!(swr_v1_reactor_socket_buffers(0, 0, 0).action, 1);
        assert_eq!(swr_v1_reactor_socket_buffers(0, 1, 1).action, 2);
        assert_eq!(swr_v1_reactor_socket_buffers(0, 2, 1).value, 1);
        for kind in [1, 2] {
            assert_eq!(swr_v1_reactor_socket_buffers(kind, 0, 0).action, 3);
            assert_eq!(swr_v1_reactor_socket_buffers(kind, 3, 0).value, 1);
        }
        assert_eq!(swr_v1_reactor_socket_timeout(4, 0, 0, 0, 1.0).action, 7);
        assert_eq!(swr_v1_reactor_socket_timeout(4, 1, 1, 0, 1.0).action, 3);
        assert_eq!(swr_v1_reactor_socket_timeout(4, 2, 1, 0, 1.0).value, 1);
    }
}
