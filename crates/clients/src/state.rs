//! `network::Client`'s connection state, which Rust owns behind an opaque handle
//! (#439), and `Client::close` and `Client::shutdown` as whole operations over it.
//! Native code keeps the `Socket`, the reactor, the timer and the `onClose`
//! callback, and passes them in `CloseOps`.
use core::ffi::c_void;

/// The `Client` flags Rust owns, for `swr_v1_clients_flag`.
pub const ACTIVE: u32 = 0;
pub const CLOSED: u32 = 1;
pub const ASYNC: u32 = 2;
pub const SHUTDOWN_READ: u32 = 3;
pub const SHUTDOWN_WRITE: u32 = 4;
pub const ASYNC_CONNECT: u32 = 5;
pub const WAIT_DNS: u32 = 6;
pub const ONERROR_CALLED: u32 = 7;

/// One client's state; native code holds it only as a pointer.
#[derive(Default)]
pub struct ClientState {
    active: bool,
    closed: bool,
    is_async: bool,
    shutdown_read: bool,
    shutdown_write: bool,
    async_connect: bool,
    wait_dns: bool,
    onerror_called: bool,
}

/// A new client's state: inactive, open, and async as constructed.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_state_new(is_async: bool) -> *mut ClientState {
    Box::into_raw(Box::new(ClientState {
        is_async,
        ..ClientState::default()
    }))
}

/// # Safety
/// `state` is null or a handle from `swr_v1_clients_state_new`, not used afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_state_free(state: *mut ClientState) {
    if !state.is_null() {
        // SAFETY: a live handle from Box::into_raw, released once (see above).
        drop(unsafe { Box::from_raw(state) });
    }
}

/// One of the flags above; false for any other.
///
/// # Safety
/// `state` is a live handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_flag(state: *const ClientState, flag: u32) -> bool {
    // SAFETY: a live handle (see above).
    let state = unsafe { &*state };
    match flag {
        ACTIVE => state.active,
        CLOSED => state.closed,
        ASYNC => state.is_async,
        SHUTDOWN_READ => state.shutdown_read,
        SHUTDOWN_WRITE => state.shutdown_write,
        ASYNC_CONNECT => state.async_connect,
        WAIT_DNS => state.wait_dns,
        ONERROR_CALLED => state.onerror_called,
        _ => false,
    }
}

/// # Safety
/// `state` is a live handle, not borrowed elsewhere during the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_set_flag(state: *mut ClientState, flag: u32, value: bool) {
    // SAFETY: a live, unborrowed handle (see above).
    let state = unsafe { &mut *state };
    match flag {
        ACTIVE => state.active = value,
        CLOSED => state.closed = value,
        ASYNC => state.is_async = value,
        SHUTDOWN_READ => state.shutdown_read = value,
        SHUTDOWN_WRITE => state.shutdown_write = value,
        ASYNC_CONNECT => state.async_connect = value,
        WAIT_DNS => state.wait_dns = value,
        ONERROR_CALLED => state.onerror_called = value,
        _ => {}
    }
}

/// `Client::shutdown(how)`: 0, -1, or -2 for native to set `EINVAL` and fail.
/// `request` is `how` as 0 `SHUT_RD`, 1 `SHUT_WR`, 2 `SHUT_RDWR`, other invalid;
/// `live` is `socket != nullptr`; `syscall` is `shutdown(2)`, called with `fd` and
/// `how` unchanged. Upstream's `SHUT_RDWR` records only a read shutdown, and so does this.
///
/// # Safety
/// `state` is a live handle, not borrowed elsewhere during the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_shutdown(
    state: *mut ClientState,
    live: bool,
    fd: i32,
    how: i32,
    request: u32,
    syscall: unsafe extern "C" fn(i32, i32) -> i32,
) -> i32 {
    // SAFETY: a live, unborrowed handle (see above).
    let state = unsafe { &mut *state };
    if !live || state.closed {
        return -1;
    }
    let call = match request {
        0 if !state.shutdown_read => 0,
        1 if !state.shutdown_write => 1,
        2 => 2,
        0 | 1 => return -1,
        _ => return -2,
    };
    // SAFETY: shutdown(2) on the client's descriptor; failure is reported by its result.
    let result = unsafe { syscall(fd, how) };
    if call == 0 && result != 0 || call != 0 && result < 0 {
        return -1;
    }
    if call == 1 {
        state.shutdown_write = true;
    } else {
        state.shutdown_read = true;
    }
    0
}

/// The client's effects for `Client::close`. Every callback gets `context`.
#[repr(C)]
pub struct CloseOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    /// The client's `Socket`, or null.
    pub socket: unsafe extern "C" fn(*mut c_void) -> *mut c_void,
    /// The TLS close (when TLS is on and live) and, for a Unix datagram socket,
    /// the unlink of its path.
    pub release: unsafe extern "C" fn(*mut c_void),
    /// Async only: the reactor removal unless already removed, then the timer's
    /// deletion if one is set.
    pub detach: unsafe extern "C" fn(*mut c_void),
    /// `onClose(this)`; false when it threw (native rethrows after this returns).
    /// The client may be gone afterwards.
    pub on_close: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Whether `socket`'s object was cleared: the client is gone or detached.
    pub orphaned: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Marks the client's current socket's descriptor closed and closes it.
    pub close_fd: unsafe extern "C" fn(*mut c_void) -> i32,
}

impl CloseOps {
    fn flag(&self, flag: u32) -> bool {
        // SAFETY: the client's live handle, read before `on_close`.
        unsafe { swr_v1_clients_flag(self.state, flag) }
    }

    fn set(&self, flag: u32, value: bool) {
        // SAFETY: the client's live handle, not borrowed across this call.
        unsafe { swr_v1_clients_set_flag(self.state, flag, value) };
    }
}

/// `Client::close()`: -1 when there is no socket or it already closed, 0 once
/// the socket was detached (or the client released) by `onClose`, otherwise
/// `close(2)`'s result.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`,
/// which `on_close` may destroy, so only `orphaned` (over the saved socket) and
/// `close_fd` (when not orphaned) run afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_close(ops: *const CloseOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    // SAFETY: a read of the live client.
    let socket = unsafe { (ops.socket)(ops.context) };
    if socket.is_null() || ops.flag(CLOSED) {
        return -1;
    }
    ops.set(CLOSED, true);
    // SAFETY: native effects on the live client.
    unsafe { (ops.release)(ops.context) };
    if ops.flag(ASYNC) {
        // SAFETY: native effects on the live client.
        unsafe { (ops.detach)(ops.context) };
        if ops.flag(ACTIVE) {
            ops.set(ACTIVE, false);
            // SAFETY: the client's last effect before the orphan check; it may destroy the client.
            if !unsafe { (ops.on_close)(ops.context) } {
                return -1;
            }
        }
    } else {
        ops.set(ACTIVE, false);
    }
    // SAFETY: reads only the socket saved before `on_close`.
    if unsafe { (ops.orphaned)(ops.context) } {
        return 0;
    }
    // SAFETY: the client is live: its socket still names it.
    unsafe { (ops.close_fd)(ops.context) }
}

#[cfg(test)]
mod tests {
    use super::*;

    unsafe extern "C" fn fake_shutdown(_: i32, how: i32) -> i32 {
        if how == libc::SHUT_WR { -1 } else { 0 }
    }

    fn shutdown(state: *mut ClientState, live: bool, how: i32) -> i32 {
        let request = match how {
            libc::SHUT_RD => 0,
            libc::SHUT_WR => 1,
            libc::SHUT_RDWR => 2,
            _ => 3,
        };
        unsafe { swr_v1_clients_shutdown(state, live, 3, how, request, fake_shutdown) }
    }

    #[test]
    fn shutdown_records_each_direction_once() {
        let state = swr_v1_clients_state_new(false);
        assert_eq!(shutdown(state, false, libc::SHUT_RD), -1);
        assert_eq!(shutdown(state, true, 99), -2);
        assert_eq!(shutdown(state, true, libc::SHUT_RD), 0);
        assert_eq!(shutdown(state, true, libc::SHUT_RD), -1);
        assert_eq!(shutdown(state, true, libc::SHUT_WR), -1);
        assert_eq!(shutdown(state, true, libc::SHUT_RDWR), 0);
        unsafe { swr_v1_clients_set_flag(state, CLOSED, true) };
        assert_eq!(shutdown(state, true, libc::SHUT_RDWR), -1);
        unsafe { swr_v1_clients_state_free(state) };
    }

    struct Fake {
        state: *mut ClientState,
        socket: bool,
        throws: bool,
        orphaned: bool,
        events: Vec<&'static str>,
    }

    unsafe fn fake<'a>(c: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *c.cast::<Fake>() }
    }
    unsafe extern "C" fn socket(c: *mut c_void) -> *mut c_void {
        if unsafe { fake(c) }.socket {
            c
        } else {
            core::ptr::null_mut()
        }
    }
    unsafe extern "C" fn release(c: *mut c_void) {
        unsafe { fake(c) }.events.push("release");
    }
    unsafe extern "C" fn detach(c: *mut c_void) {
        unsafe { fake(c) }.events.push("detach");
    }
    unsafe extern "C" fn on_close(c: *mut c_void) -> bool {
        let this = unsafe { fake(c) };
        this.events.push("on-close");
        !this.throws
    }
    unsafe extern "C" fn orphaned(c: *mut c_void) -> bool {
        unsafe { fake(c) }.orphaned
    }
    unsafe extern "C" fn close_fd(c: *mut c_void) -> i32 {
        unsafe { fake(c) }.events.push("close-fd");
        0
    }

    fn close(
        is_async: bool,
        active: bool,
        setup: impl FnOnce(&mut Fake),
    ) -> (i32, Vec<&'static str>, bool) {
        let mut fake = Fake {
            state: swr_v1_clients_state_new(is_async),
            socket: true,
            throws: false,
            orphaned: false,
            events: Vec::new(),
        };
        unsafe { swr_v1_clients_set_flag(fake.state, ACTIVE, active) };
        setup(&mut fake);
        let ops = CloseOps {
            context: (&raw mut fake).cast(),
            state: fake.state,
            socket,
            release,
            detach,
            on_close,
            orphaned,
            close_fd,
        };
        let result = unsafe { swr_v1_clients_close(&raw const ops) };
        let active = unsafe { swr_v1_clients_flag(fake.state, ACTIVE) };
        unsafe { swr_v1_clients_state_free(fake.state) };
        (result, fake.events, active)
    }

    #[test]
    fn sync_close_deactivates_and_closes_the_descriptor() {
        assert_eq!(
            close(false, true, |_| {}),
            (0, vec!["release", "close-fd"], false)
        );
        assert_eq!(close(false, true, |f| f.socket = false), (-1, vec![], true));
    }

    #[test]
    fn async_close_detaches_then_calls_on_close_once() {
        assert_eq!(
            close(true, true, |_| {}),
            (0, vec!["release", "detach", "on-close", "close-fd"], false)
        );
        assert_eq!(
            close(true, false, |_| {}),
            (0, vec!["release", "detach", "close-fd"], false)
        );
        assert_eq!(
            close(true, true, |f| f.orphaned = true),
            (0, vec!["release", "detach", "on-close"], false)
        );
        assert_eq!(
            close(true, true, |f| f.throws = true),
            (-1, vec!["release", "detach", "on-close"], false)
        );
    }

    #[test]
    fn a_closed_client_is_not_closed_again() {
        assert_eq!(
            close(false, true, |f| unsafe {
                swr_v1_clients_set_flag(f.state, CLOSED, true);
            }),
            (-1, vec![], true)
        );
    }
}
