//! `System::wait_event(fd, events, timeout)`: wait until `fd` is readable and/or
//! writable. A zero timeout is one `poll(2)` here; otherwise native code parks the
//! coroutine on the reactor (`EventWaiter`) through `EventWait`. Native code keeps
//! setting errno and the last error from the outcome.
use crate::swr_v1_hook_wait_revents;

/// `SW_EVENT_READ`, `SW_EVENT_WRITE` and `SW_EVENT_ERROR`.
pub(crate) const READ: i32 = 1 << 9;
pub(crate) const WRITE: i32 = 1 << 10;
pub(crate) const ERROR: i32 = 1 << 11;

/// Parks the current coroutine until `events` fire on `fd` or `timeout` passes,
/// storing the fired events; returns the error, or 0.
pub type EventWait = unsafe extern "C" fn(i32, i32, f64, *mut i32) -> i32;

/// What `wait_event` returns.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct WaitEvent {
    /// The fired events, or -1.
    pub result: i32,
    /// For native to set as the last error, or 0.
    pub last_error: i32,
    /// For native to set as errno, or 0.
    pub error: i32,
}

const fn failed(last_error: i32, error: i32) -> WaitEvent {
    WaitEvent {
        result: -1,
        last_error,
        error,
    }
}

/// `translate_events_to_poll`.
pub(crate) fn to_poll(events: i32) -> i16 {
    let mut poll = 0;
    if events & READ != 0 {
        poll |= libc::POLLIN;
    }
    if events & WRITE != 0 {
        poll |= libc::POLLOUT;
    }
    poll
}

/// `translate_events_from_poll`: error and hang-up count only without IN/OUT.
pub(crate) fn from_poll(revents: i16) -> i32 {
    let mut events = 0;
    if revents & libc::POLLIN != 0 {
        events |= READ;
    }
    if revents & libc::POLLOUT != 0 {
        events |= WRITE;
    }
    if revents & (libc::POLLERR | libc::POLLHUP) != 0
        && revents & (libc::POLLIN | libc::POLLOUT) == 0
    {
        events |= ERROR;
    }
    events
}

/// Waits for `events` (only `SW_EVENT_READ`/`WRITE` count) on `fd`.
///
/// # Safety
/// `wait` is native's `EventWaiter` wait, callable in the current coroutine.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_wait_event(
    fd: i32,
    events: i32,
    timeout: f64,
    wait: EventWait,
) -> WaitEvent {
    let events = events & (READ | WRITE);
    if events == 0 {
        return failed(libc::EINVAL, 0);
    }
    if timeout == 0.0 {
        let mut pfd = libc::pollfd {
            fd,
            events: to_poll(events),
            revents: 0,
        };
        // SAFETY: `pfd` is one valid pollfd.
        let ready = unsafe { libc::poll(&raw mut pfd, 1, 0) };
        if ready == 1 {
            if pfd.revents & libc::POLLNVAL != 0 {
                return failed(libc::EBADF, 0);
            }
            return WaitEvent {
                result: from_poll(pfd.revents),
                ..WaitEvent::default()
            };
        }
        let error = if ready < 0 {
            std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
        } else {
            libc::ETIMEDOUT
        };
        return failed(error, 0);
    }
    let mut fired = 0;
    // SAFETY: the caller passes the native wait; `fired` is writable.
    let error = unsafe { wait(fd, events, timeout, &raw mut fired) };
    if error != 0 {
        return failed(0, error);
    }
    let read_write = (READ | WRITE).cast_unsigned();
    let result = swr_v1_hook_wait_revents(
        events.cast_unsigned(),
        fired.cast_unsigned(),
        read_write,
        ERROR.cast_unsigned(),
    );
    WaitEvent {
        result: result.cast_signed(),
        ..WaitEvent::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    unsafe extern "C" fn unused(_: i32, _: i32, _: f64, _: *mut i32) -> i32 {
        unreachable!()
    }
    unsafe extern "C" fn fires_error(_: i32, _: i32, _: f64, fired: *mut i32) -> i32 {
        unsafe { *fired = ERROR };
        0
    }
    unsafe extern "C" fn times_out(_: i32, _: i32, _: f64, _: *mut i32) -> i32 {
        libc::ETIMEDOUT
    }

    fn wait(fd: i32, events: i32, timeout: f64, how: EventWait) -> WaitEvent {
        unsafe { swr_v1_hook_wait_event(fd, events, timeout, how) }
    }

    #[test]
    fn polls_now_or_parks() {
        let mut fds = [0; 2];
        assert_eq!(unsafe { libc::pipe(fds.as_mut_ptr()) }, 0);
        let [reader, writer] = fds;
        let ok = |result| WaitEvent {
            result,
            ..WaitEvent::default()
        };

        assert_eq!(wait(reader, ERROR, 0.0, unused), failed(libc::EINVAL, 0));
        assert_eq!(wait(reader, READ, 0.0, unused), failed(libc::ETIMEDOUT, 0));
        assert_eq!(wait(writer, WRITE | ERROR, 0.0, unused), ok(WRITE));
        assert_eq!(unsafe { libc::write(writer, b"x".as_ptr().cast(), 1) }, 1);
        assert_eq!(wait(reader, READ | WRITE, 0.0, unused), ok(READ));
        unsafe { libc::close(writer) };
        assert_eq!(
            unsafe { libc::read(reader, [0u8; 1].as_mut_ptr().cast(), 1) },
            1
        );
        assert!(wait(reader, READ, 0.0, unused).result & (READ | ERROR) != 0);
        unsafe { libc::close(reader) };
        // Never open, so poll reports POLLNVAL (a just-closed fd may be reused).
        assert_eq!(wait(100_000, READ, 0.0, unused), failed(libc::EBADF, 0));

        assert_eq!(wait(7, READ, 1.0, fires_error), ok(READ));
        assert_eq!(wait(7, READ, -1.0, times_out), failed(0, libc::ETIMEDOUT));
    }
}
