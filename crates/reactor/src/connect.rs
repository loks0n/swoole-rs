//! Complete ordinary connect sequencing. Native owns Socket/Address, syscalls,
//! errno, timeout conversion and publication; no reference spans an effect.
use crate::ReactorOutputAction;

fn reply(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}

/// operation0 async,1 sync. Actions0 return,1 nonblock,2 connect,3 errno fact,
///4 last-error(current errno),5 connect_async,6 timeout fact,7 sec2msec conversion,
///8 direct timeout conversion,9 wait,10 last-error(ETIMEDOUT),11 SO_ERROR call,
///12 SO_ERROR output fact,13 last-error(output),14 block. All effects are Native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_socket_connect(
    operation: u32,
    phase: u32,
    observed: i32,
    timeout: f64,
) -> ReactorOutputAction {
    match (operation, phase) {
        (0, 0) => reply(1, 1, 0),
        (0, 1) => reply(2, 2, 0),
        (0, 2) if observed < 0 => reply(3, 3, 0),
        (0, 2) => reply(100, 0, 5), // READY
        (0, 3) if observed == libc::EINTR => reply(2, 2, 0),
        (0, 3) => reply(4, 4, 0),
        (0, 4) => reply(5, 3, 0), // fresh errno after last-error publication
        (0, 5) => reply(100, 0, if observed == libc::EINPROGRESS { 2 } else { 4 }),
        (1, 0) => reply(1, 5, 0),
        (1, 1) if observed != 2 => reply(100, 0, if observed == 5 { 0 } else { -1 }),
        (1, 1) => reply(2, 6, 0),
        (1, 2) => reply(3, if timeout > 0.0 { 7 } else { 8 }, 0),
        (1, 3) => reply(4, 9, 0),
        (1, 4) if observed < 0 => reply(10, 10, 0),
        (1, 4) => reply(5, 11, 0),
        (1, 5) if observed < 0 => reply(10, 4, 0),
        (1, 5) => reply(6, 12, 0),
        (1, 6) if observed != 0 => reply(10, 13, 0),
        (1, 6) => reply(7, 14, 0),
        (1, 7) => reply(100, 0, 0),
        (1, 10) => reply(100, 0, -1),
        _ => reply(phase, -1, 0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(operation: u32, phase: u32, observed: i32, timeout: f64, expected: (u32, i32, i64)) {
        let result = swr_v1_reactor_socket_connect(operation, phase, observed, timeout);
        assert_eq!((result.phase, result.action, result.value), expected);
    }

    #[test]
    fn connect_positive_complete_paths() {
        for (op, phase, observed, expected) in [
            (0, 0, 0, (1, 1, 0)),
            (0, 1, 0, (2, 2, 0)),
            (0, 2, 0, (100, 0, 5)),
            (1, 0, 0, (1, 5, 0)),
            (1, 1, 5, (100, 0, 0)),
            (1, 1, 2, (2, 6, 0)),
            (1, 3, 0, (4, 9, 0)),
            (1, 4, 0, (5, 11, 0)),
            (1, 5, 0, (6, 12, 0)),
            (1, 6, 0, (7, 14, 0)),
            (1, 7, 0, (100, 0, 0)),
        ] {
            check(op, phase, observed, 0.0, expected);
        }
        for timeout in [-1.0, -0.0, 0.0, 0.25] {
            check(1, 2, 0, timeout, (3, if timeout > 0.0 { 7 } else { 8 }, 0));
        }
    }

    #[test]
    fn connect_scalar_only_routing_preserves_fresh_observations() {
        // Integer facts only: no syscall, errno read, setter, signal or Native effect.
        check(0, 2, -1, 0.0, (3, 3, 0));
        check(0, 3, libc::EINTR, 0.0, (2, 2, 0));
        check(0, 3, libc::EINPROGRESS, 0.0, (4, 4, 0));
        check(0, 4, 0, 0.0, (5, 3, 0));
        check(0, 5, libc::EINPROGRESS, 0.0, (100, 0, 2));
        check(0, 5, 0, 0.0, (100, 0, 4));
        check(1, 1, 4, 0.0, (100, 0, -1));
        check(1, 4, -1, 0.0, (10, 10, 0));
        check(1, 5, -1, 0.0, (10, 4, 0));
        check(1, 6, 7, 0.0, (10, 13, 0));
        check(1, 10, 0, 0.0, (100, 0, -1));
    }
}
