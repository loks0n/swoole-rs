//! Whole fcntl option ordering. Native retains descriptors, actual fcntl calls,
//! errno, warning/exception effects and its two result locals.
use crate::ReactorOutputAction;
fn out(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
fn descriptor(cloexec: i32, available: u32) -> ReactorOutputAction {
    if available != 0 && cloexec >= 0 {
        out(7, 6, 0)
    } else {
        out(100, 0, 1)
    }
}
fn status_flags(opts: i32, nonblock: i32) -> ReactorOutputAction {
    out(
        4,
        4,
        (if nonblock != 0 {
            opts | libc::O_NONBLOCK
        } else {
            opts & !libc::O_NONBLOCK
        })
        .into(),
    )
}
fn descriptor_flags(opts: i32, cloexec: i32) -> ReactorOutputAction {
    out(
        10,
        8,
        (if cloexec != 0 {
            opts | libc::FD_CLOEXEC
        } else {
            opts & !libc::FD_CLOEXEC
        })
        .into(),
    )
}
/// Actions:0 return,1 GETFL,2 errno fact,3 GETFL warning,4 SETFL,
///5 SETFL warning,6 GETFD,7 original GETFL warning at GETFD site,8 SETFD,
///9 SETFD warning. Return values are Native bool. Native executes all effects
/// after return; no loop or borrowed descriptor/errno storage crosses the ABI.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_fd_options(
    phase: u32,
    opts: i32,
    result: i32,
    observed: i32,
    nonblock: i32,
    cloexec: i32,
    available: u32,
) -> ReactorOutputAction {
    match phase {
        0 if nonblock >= 0 => out(1, 1, 0),
        0 => descriptor(cloexec, available),
        1 if opts < 0 => out(2, 2, 0),
        1 | 3 => status_flags(opts, nonblock),
        2 if observed == libc::EINTR => out(1, 1, 0),
        2 => out(3, 3, 0),
        4 if result < 0 => out(5, 2, 0),
        4 => descriptor(cloexec, available),
        5 if observed == libc::EINTR => out(4, 4, opts.into()),
        5 => out(6, 5, 0),
        6 | 12 => out(100, 0, 0),
        7 if opts < 0 => out(8, 2, 0),
        7 | 9 => descriptor_flags(opts, cloexec),
        8 if observed == libc::EINTR => out(7, 6, 0),
        8 => out(9, 7, 0),
        10 if result < 0 => out(11, 2, 0),
        10 => out(100, 0, 1),
        11 if observed == libc::EINTR => out(10, 8, opts.into()),
        11 => out(12, 9, 0),
        _ => out(phase, -1, 0),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fd_options_positive_short_circuits_and_bit_preservation() {
        assert_eq!(swr_v1_reactor_fd_options(0, 0, 0, 0, -1, -1, 1).value, 1);
        assert_eq!(swr_v1_reactor_fd_options(0, 0, 0, 0, -1, 1, 0).value, 1);
        assert_eq!(swr_v1_reactor_fd_options(0, 0, 0, 0, 0, 1, 1).action, 1);
        assert_eq!(swr_v1_reactor_fd_options(0, 0, 0, 0, -1, 1, 1).action, 6);
        for value in [
            0,
            libc::O_APPEND,
            libc::O_NONBLOCK,
            libc::O_APPEND | libc::O_NONBLOCK,
        ] {
            let enabled = swr_v1_reactor_fd_options(1, value, 0, 0, 1, -1, 1);
            assert_eq!(enabled.value, (value | libc::O_NONBLOCK) as i64);
            let disabled = swr_v1_reactor_fd_options(1, value, 0, 0, 0, -1, 1);
            assert_eq!(disabled.value, (value & !libc::O_NONBLOCK) as i64);
        }
        assert_eq!(
            swr_v1_reactor_fd_options(7, 0, 0, 0, -1, 1, 1).value,
            libc::FD_CLOEXEC as i64
        );
    }
}
