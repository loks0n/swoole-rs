//! `Socket::wait_event` of the coroutine socket and its readable and writable
//! reactor callbacks, over the Rust-owned state: which event to add (a TLS session
//! may want the other direction), binding the coroutine for the wait, the barrier
//! that retries a transfer before the waiter wakes, and removing the event after.
//! Native code keeps the reactor, the coroutine switch and the write buffer, and
//! passes them in `WaitOps`.
use crate::shutdown::{READ, SocketState, WRITE, swr_v1_hook_socket_bind, swr_v1_hook_socket_co};
use crate::vector::Barrier;
use core::ffi::c_void;

/// `status` bits; the socket's `events` arrive in the `READ` and `WRITE` bits.
pub const CLOSE_WAIT: u32 = 1;
pub const NOBUFS: u32 = 1 << 1;
pub const WANT_READ: u32 = 1 << 2;
pub const WANT_WRITE: u32 = 1 << 3;
pub const REMOVED: u32 = 1 << 4;

/// The socket's effects. Every callback gets `context`.
#[repr(C)]
pub struct WaitOps {
    pub context: *mut c_void,
    pub state: *mut SocketState,
    /// `SW_ERROR_CO_SOCKET_CLOSE_WAIT`.
    pub close_wait_error: i32,
    /// `close_wait`, else `has_kernel_nobufs()` (which clears it); the TLS
    /// session's wants, `removed` and `events`.
    pub status: unsafe extern "C" fn(*mut c_void) -> u32,
    pub closed: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `errCode`.
    pub error: unsafe extern "C" fn(*mut c_void) -> i32,
    pub set_err: unsafe extern "C" fn(*mut c_void, i32),
    /// `System::sleep(0.01)`.
    pub sleep: unsafe extern "C" fn(*mut c_void),
    /// `swoole_event_add(events)` when `add`, else `swoole_event_set(events)`;
    /// false, with errno set, on failure.
    pub reactor: unsafe extern "C" fn(*mut c_void, u32, bool) -> bool,
    /// Yields `co` with `cancel(event)` as its cancel function.
    pub suspend: unsafe extern "C" fn(*mut c_void, *mut c_void, u32),
    /// Moves a write's `length` bytes at `*buffer` to the write buffer unless they
    /// are there already or the socket is zero-copy.
    pub buffer: unsafe extern "C" fn(*mut c_void, *mut *mut u8, usize),
    /// `remove_read_event`/`remove_write_event`.
    pub remove: unsafe extern "C" fn(*mut c_void, u32),
}

fn slot(event: u32) -> usize {
    usize::from(event == WRITE)
}

impl WaitOps {
    fn set_err(&self, error: i32) {
        // SAFETY: a native effect on the live socket in `context`.
        unsafe { (self.set_err)(self.context, error) };
    }

    fn bind(&self, event: u32, co: *mut c_void) {
        // SAFETY: the socket's live handle, not borrowed across this call.
        unsafe { swr_v1_hook_socket_bind(self.state, event, co) };
    }

    fn want(&self) -> u32 {
        // SAFETY: a read of the live handle.
        unsafe { (*self.state).want }
    }

    fn set_want(&self, event: u32) {
        // SAFETY: a write to the live handle, not borrowed across this call.
        unsafe { (*self.state).want = event };
    }

    fn set_barrier(&self, event: u32, barrier: Option<(Barrier, *mut c_void)>) {
        // SAFETY: a write to the live handle, not borrowed across this call.
        unsafe { (*self.state).barriers[slot(event)] = barrier };
    }

    fn closed(&self) -> bool {
        // SAFETY: a read of the live socket.
        unsafe { (self.closed)(self.context) }
    }

    /// `add_event`: add `event` to the reactor unless it is there already.
    fn add(&self, status: u32, event: u32) -> bool {
        let removed = status & REMOVED != 0;
        let events = if removed {
            event
        } else {
            status & (READ | WRITE) | event
        };
        // SAFETY: a native effect on the live socket's reactor registration.
        let added = status & event != 0 || unsafe { (self.reactor)(self.context, events, removed) };
        self.set_err(if added {
            0
        } else {
            std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
        });
        added
    }

    fn wait(&self, co: *mut c_void, event: u32, buffer: *mut *mut u8, length: usize) -> bool {
        // SAFETY: a read of the live socket; it clears the kernel no-buffers flag.
        let status = unsafe { (self.status)(self.context) };
        if status & CLOSE_WAIT != 0 {
            self.set_err(self.close_wait_error);
            return false;
        }
        let event = if event == READ { READ } else { WRITE };
        if status & NOBUFS != 0 {
            self.bind(event, co);
            // SAFETY: a native coroutine sleep; this coroutine stays bound across it.
            unsafe { (self.sleep)(self.context) };
            self.bind(event, core::ptr::null_mut());
            return !self.closed();
        }
        self.set_err(0);
        let mut added = event;
        if event == READ && status & WANT_WRITE != 0 || event == WRITE && status & WANT_READ != 0 {
            if status & WANT_WRITE != 0 && self.add(status, WRITE) {
                self.set_want(WRITE);
            } else if status & WANT_READ != 0 && self.add(status, READ) {
                self.set_want(READ);
            } else {
                return false;
            }
            added = self.want();
        } else if !self.add(status, event) {
            return false;
        }
        if event == WRITE && !buffer.is_null() {
            // SAFETY: the caller's live buffer slot of `length` bytes.
            unsafe { (self.buffer)(self.context, buffer, length) };
        }
        self.bind(event, co);
        // SAFETY: suspends this coroutine until a callback, timer or cancel resumes it.
        unsafe { (self.suspend)(self.context, co, event) };
        self.bind(event, core::ptr::null_mut());
        // Both coroutines may wait for the same event under TLS.
        // SAFETY: a read of the live handle.
        let bound = unsafe {
            !crate::shutdown::swr_v1_hook_socket_bound_co(self.state, READ | WRITE).is_null()
        };
        if self.want() == 0 || !bound {
            // SAFETY: a native effect on the live socket's reactor registration.
            unsafe { (self.remove)(self.context, added) };
        }
        self.set_want(0);
        // SAFETY: a read of the live socket.
        !self.closed() && unsafe { (self.error)(self.context) } == 0
    }
}

/// `Socket::wait_event(event)` for the current coroutine `co`, with `barrier`
/// (and its state) retrying the transfer while it is installed. `buffer`, when not
/// null, is a write's buffer slot, which may move to the socket's write buffer.
/// True when woken with the socket open and no error.
///
/// # Safety
/// `ops` is live for the call; `barrier_state` outlives it; `buffer` is null or a
/// live slot of `length` bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_socket_wait(
    ops: *const WaitOps,
    co: *mut c_void,
    event: u32,
    barrier: Option<Barrier>,
    barrier_state: *mut c_void,
    buffer: *mut *mut u8,
    length: usize,
) -> bool {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let Some(barrier) = barrier else {
        return ops.wait(co, event, buffer, length);
    };
    ops.set_barrier(event, Some((barrier, barrier_state)));
    let woke = ops.wait(co, event, buffer, length);
    ops.set_barrier(event, None);
    woke
}

/// The readable (`event` read) or writable callback: the coroutine to resume, or
/// null. Under a TLS wait the other direction's coroutine wakes; otherwise an
/// installed barrier that keeps waiting holds the coroutine unless the peer hung up.
///
/// # Safety
/// `state` is a live handle; an installed barrier's state is live.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_socket_ready(
    state: *mut SocketState,
    event: u32,
    hup: bool,
) -> *mut c_void {
    let other = if event == READ { WRITE } else { READ };
    // SAFETY: a read of the live handle.
    let want = unsafe { (*state).want };
    // SAFETY: a read of the live handle.
    let barrier = unsafe { (*state).barriers[slot(event)] };
    if want != 0 {
        return if want == event {
            // SAFETY: a read of the live handle.
            unsafe { swr_v1_hook_socket_co(state, other) }
        } else {
            core::ptr::null_mut()
        };
    }
    if let Some((barrier, barrier_state)) = barrier {
        // SAFETY: the installed barrier with its live state; it does not touch `state`'s
        // barriers or bindings.
        if unsafe { barrier(barrier_state) } && !hup {
            return core::ptr::null_mut();
        }
    }
    // SAFETY: a read of the live handle.
    unsafe { swr_v1_hook_socket_co(state, event) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shutdown::{swr_v1_hook_socket_state_free, swr_v1_hook_socket_state_new};

    struct Fake {
        state: *mut SocketState,
        status: u32,
        error: i32,
        closed: bool,
        reactor_ok: bool,
        events: Vec<String>,
    }

    impl Fake {
        fn new(status: u32) -> Self {
            Self {
                state: swr_v1_hook_socket_state_new(),
                status,
                error: 0,
                closed: false,
                reactor_ok: true,
                events: Vec::new(),
            }
        }
    }

    impl Drop for Fake {
        fn drop(&mut self) {
            unsafe { swr_v1_hook_socket_state_free(self.state) };
        }
    }

    unsafe fn fake<'a>(c: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *c.cast::<Fake>() }
    }

    unsafe extern "C" fn status(c: *mut c_void) -> u32 {
        unsafe { fake(c) }.status
    }
    unsafe extern "C" fn closed(c: *mut c_void) -> bool {
        unsafe { fake(c) }.closed
    }
    unsafe extern "C" fn error(c: *mut c_void) -> i32 {
        unsafe { fake(c) }.error
    }
    unsafe extern "C" fn set_err(c: *mut c_void, e: i32) {
        unsafe { fake(c) }.error = e;
    }
    unsafe extern "C" fn sleep(c: *mut c_void) {
        let this = unsafe { fake(c) };
        let bound = unsafe { !swr_v1_hook_socket_co(this.state, WRITE).is_null() };
        this.events.push(format!("sleep:{bound}"));
    }
    unsafe extern "C" fn reactor(c: *mut c_void, events: u32, add: bool) -> bool {
        let this = unsafe { fake(c) };
        this.events
            .push(format!("{}:{events}", if add { "add" } else { "set" }));
        this.reactor_ok
    }
    unsafe extern "C" fn suspend(c: *mut c_void, co: *mut c_void, event: u32) {
        let this = unsafe { fake(c) };
        let state = this.state;
        let woken = unsafe { swr_v1_hook_socket_ready(state, event, false) };
        this.events.push(format!("yield:{}", woken == co));
    }
    unsafe extern "C" fn buffer(c: *mut c_void, _: *mut *mut u8, n: usize) {
        unsafe { fake(c) }.events.push(format!("buffer:{n}"));
    }
    unsafe extern "C" fn remove(c: *mut c_void, event: u32) {
        unsafe { fake(c) }.events.push(format!("remove:{event}"));
    }

    fn ops(fake: &mut Fake) -> WaitOps {
        WaitOps {
            context: (&raw mut *fake).cast(),
            state: fake.state,
            close_wait_error: 1777,
            status,
            closed,
            error,
            set_err,
            sleep,
            reactor,
            suspend,
            buffer,
            remove,
        }
    }

    fn wait(fake: &mut Fake, event: u32, barrier: Option<Barrier>) -> bool {
        let table = ops(fake);
        let mut co = 7u8;
        let mut slot = core::ptr::null_mut();
        unsafe {
            swr_v1_hook_socket_wait(
                &raw const table,
                (&raw mut co).cast(),
                event,
                barrier,
                core::ptr::null_mut(),
                &raw mut slot,
                4,
            )
        }
    }

    #[test]
    fn a_plain_wait_adds_binds_yields_and_removes() {
        let mut fake = Fake::new(READ);
        assert!(wait(&mut fake, WRITE, None));
        assert_eq!(
            fake.events,
            ["set:1536", "buffer:4", "yield:true", "remove:1024"]
        );
        let mut fake = Fake::new(REMOVED);
        assert!(wait(&mut fake, READ, None));
        assert_eq!(fake.events, ["add:512", "yield:true", "remove:512"]);
    }

    #[test]
    fn close_wait_nobufs_and_reactor_failures_stop_early() {
        let mut fake = Fake::new(CLOSE_WAIT | NOBUFS);
        assert!(!wait(&mut fake, READ, None));
        assert_eq!((fake.error, fake.events.len()), (1777, 0));
        let mut fake = Fake::new(NOBUFS);
        assert!(wait(&mut fake, WRITE, None));
        assert_eq!(fake.events, ["sleep:true"]);
        let mut fake = Fake::new(0);
        fake.reactor_ok = false;
        assert!(!wait(&mut fake, READ, None));
        assert_eq!(fake.events, ["set:512"]);
    }

    #[test]
    fn tls_waits_for_the_direction_it_wants() {
        let mut fake = Fake::new(WANT_WRITE);
        assert!(wait(&mut fake, READ, None));
        // The writable callback wakes the reader; no one else is bound, so remove.
        assert_eq!(fake.events, ["set:1024", "yield:false", "remove:1024"]);
        assert_eq!(unsafe { (*fake.state).want }, 0);
    }

    #[test]
    fn a_barrier_that_keeps_waiting_holds_the_coroutine() {
        unsafe extern "C" fn again(_: *mut c_void) -> bool {
            true
        }
        let mut fake = Fake::new(0);
        assert!(wait(&mut fake, READ, Some(again)));
        assert_eq!(fake.events, ["set:512", "yield:false", "remove:512"]);
        assert!(unsafe { (*fake.state).barriers[0] }.is_none());
    }

    #[test]
    fn a_wake_with_an_error_or_close_fails() {
        let mut fake = Fake::new(0);
        fake.closed = true;
        assert!(!wait(&mut fake, READ, None));
    }
}
