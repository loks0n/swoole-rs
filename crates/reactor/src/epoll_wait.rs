//! The whole epoll wait loop in one call (#336). Rust owns the loop and readiness order;
//! native code supplies only the effects upstream also reaches through `Reactor` members.
use std::ffi::{c_int, c_void};

/// Native effects for one `ReactorEpoll::wait`. Every function receives `reactor`.
#[repr(C)]
pub struct EpollWaitOps {
    pub reactor: *mut c_void,
    pub events: *mut libc::epoll_event,
    pub epfd: c_int,
    /// `Reactor::running`, `once` and `max_event_num`, read fresh on every use.
    pub running: *const bool,
    pub once: *const bool,
    pub max_events: *const u32,
    /// The kernel wait (`epoll_wait`), passed in so a test harness can substitute it.
    pub kernel_wait: unsafe extern "C" fn(c_int, *mut libc::epoll_event, c_int, c_int) -> c_int,
    pub before_wait: unsafe extern "C" fn(*mut c_void),
    pub begin: unsafe extern "C" fn(*mut c_void),
    pub timeout: unsafe extern "C" fn(*mut c_void) -> c_int,
    pub catch_error: unsafe extern "C" fn(*mut c_void) -> c_int,
    pub end: unsafe extern "C" fn(*mut c_void, c_int),
    /// The io_uring EINTR handler, if the build has one: `interrupt` runs it when `interrupted`.
    pub interrupted: Option<unsafe extern "C" fn(*mut c_void) -> c_int>,
    pub interrupt: Option<unsafe extern "C" fn(*mut c_void)>,
    pub wait_failed: unsafe extern "C" fn(*mut c_void),
    /// Fill the native `Event` for `socket`, marking `event_hup` when `hup` is nonzero.
    pub prepare: unsafe extern "C" fn(*mut c_void, *mut c_void, c_int),
    /// `socket->removed`, and `socket->events & SW_EVENT_ONCE`.
    pub removed: unsafe extern "C" fn(*mut c_void) -> c_int,
    pub oneshot: unsafe extern "C" fn(*mut c_void) -> c_int,
    /// Run the read (0), write (1) or error (2) handler for the prepared event.
    pub handle: unsafe extern "C" fn(*mut c_void, u32) -> c_int,
    /// Warn that handler `kind` failed for the prepared event.
    pub handler_failed: unsafe extern "C" fn(*mut c_void, u32),
    pub remove: unsafe extern "C" fn(*mut c_void, *mut c_void),
}

const READ: u32 = libc::EPOLLIN as u32;
const WRITE: u32 = libc::EPOLLOUT as u32;
const HANGUP: u32 = (libc::EPOLLRDHUP | libc::EPOLLERR | libc::EPOLLHUP) as u32;

/// Upstream's `ReactorEpoll::wait`: 0 when the loop stops, -1 when `epoll_wait` fails uncaught.
/// # Safety
/// `ops` is live for the call and its pointers are valid: `events` holds `max_events` entries,
/// the field pointers stay readable, and every function accepts `reactor` (and the event socket).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_epoll_run(ops: *const EpollWaitOps) -> i32 {
    // SAFETY: per the contract, `ops` is live for this call.
    let ops = unsafe { &*ops };
    let reactor = ops.reactor;
    // SAFETY: the native effect accepts `reactor`.
    unsafe { (ops.before_wait)(reactor) };
    // SAFETY: the field pointers stay readable for the call; handlers may change them.
    while unsafe { ops.running.read() } {
        // SAFETY: the native effect accepts `reactor`.
        unsafe { (ops.begin)(reactor) };
        // SAFETY: the field pointer stays readable for the call.
        let capacity = c_int::try_from(unsafe { ops.max_events.read() }).unwrap_or(c_int::MAX);
        // SAFETY: the native effect accepts `reactor`.
        let timeout = unsafe { (ops.timeout)(reactor) };
        // SAFETY: `events` holds `max_events` entries for the kernel to fill.
        let ready = unsafe { (ops.kernel_wait)(ops.epfd, ops.events, capacity, timeout) };
        if ready < 0 {
            // SAFETY: the native effect accepts `reactor` and reads this thread's errno.
            if unsafe { (ops.catch_error)(reactor) } == 0 {
                // SAFETY: the native effect accepts `reactor`.
                unsafe { (ops.wait_failed)(reactor) };
                return -1;
            }
            if let (Some(interrupted), Some(interrupt)) = (ops.interrupted, ops.interrupt) {
                // SAFETY: both native effects accept `reactor`.
                if unsafe { interrupted(reactor) } != 0 {
                    // SAFETY: the native effect accepts `reactor`.
                    unsafe { interrupt(reactor) };
                }
            }
        } else if ready == 0 {
            // SAFETY: the native effect accepts `reactor`.
            unsafe { (ops.end)(reactor, 1) };
            // SAFETY: the field pointer stays readable for the call.
            if unsafe { ops.once.read() } {
                break;
            }
            continue;
        } else {
            for index in 0..ready.unsigned_abs() as usize {
                let entry = ops.events.wrapping_add(index);
                // SAFETY: the kernel filled the first `ready` entries of `events`.
                let entry = unsafe { entry.read_unaligned() };
                dispatch(ops, entry);
            }
        }
        // SAFETY: the native effect accepts `reactor`.
        unsafe { (ops.end)(reactor, 0) };
        // SAFETY: the field pointer stays readable for the call.
        if unsafe { ops.once.read() } {
            break;
        }
    }
    0
}

/// One ready socket, in upstream's order: read, write, error, then a oneshot removal.
fn dispatch(ops: &EpollWaitOps, entry: libc::epoll_event) {
    let reactor = ops.reactor;
    let mask = entry.events;
    #[expect(
        clippy::cast_possible_truncation,
        reason = "the token is a pointer stored in u64"
    )]
    let socket = entry.u64 as usize as *mut c_void;
    // SAFETY: `socket` is the registered native socket; the effect accepts it.
    unsafe { (ops.prepare)(reactor, socket, c_int::from(mask & HANGUP != 0)) };
    // SAFETY: `socket` stays live while its handlers run.
    let live = || unsafe { (ops.removed)(socket) } == 0;
    for (kind, bit) in [(0, READ), (1, WRITE)] {
        // SAFETY: the native effect accepts `reactor` and the prepared event.
        if mask & bit != 0 && live() && unsafe { (ops.handle)(reactor, kind) } < 0 {
            // SAFETY: the native effect accepts `reactor` and the prepared event.
            unsafe { (ops.handler_failed)(reactor, kind) };
        }
    }
    if mask & HANGUP != 0 && live() {
        // The read or write handler has already seen the error or hangup.
        if mask & (READ | WRITE) != 0 {
            return;
        }
        // SAFETY: the native effect accepts `reactor` and the prepared event.
        if unsafe { (ops.handle)(reactor, 2) } < 0 {
            // SAFETY: the native effect accepts `reactor` and the prepared event.
            unsafe { (ops.handler_failed)(reactor, 2) };
        }
    }
    // SAFETY: `socket` stays live until its removal below.
    if live() && unsafe { (ops.oneshot)(socket) } != 0 {
        // SAFETY: the native effect accepts `reactor` and the socket.
        unsafe { (ops.remove)(reactor, socket) };
    }
}
