//! `network::Socket`'s queued output: `handle_send` sends the front data chunk and
//! classifies the result; `handle_sendfile` corks, then classifies and completes
//! the front file request around native code's sendfile call (where the optional
//! halfclose repair sits); `sendfile_async` queues a file. Native code owns the
//! buffer, its chunks and the requests, and performs each effect through
//! [`OutputHooks`].
use std::io::Error;
use std::os::raw::{c_int, c_void};

/// `swReturnCode`: `SW_WAIT`, `SW_CLOSE`, `SW_ERROR`; and `SW_OK`/`SW_ERR`.
const WAIT: c_int = 2;
const CLOSE: c_int = 3;
const ERROR: c_int = 4;
const OK: c_int = 0;
const ERR: c_int = -1;

/// What queued output needs from its native `Socket`.
#[repr(C)]
pub struct OutputHooks {
    pub socket: *mut c_void,
    /// `Socket::kernel_nobufs`, which `catch_error` sets on ENOBUFS.
    pub kernel_nobufs: *mut bool,
    /// `Socket::send(data, length, 0)`.
    pub send:
        unsafe extern "C" fn(socket: *mut c_void, data: *const c_void, length: usize) -> isize,
    pub cork: unsafe extern "C" fn(socket: *mut c_void) -> bool,
    pub uncork: unsafe extern "C" fn(socket: *mut c_void),
    /// Records the send time when the socket has a send timer.
    pub sent: unsafe extern "C" fn(socket: *mut c_void),
}

/// What native code applies after `handle_send`/`handle_sendfile`: pop the front
/// chunk, store `offset` into it, set `close_wait`/`send_wait`, and warn (1 the data
/// send failed, 2 the sendfile of `requested` bytes failed). `code` is returned.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct OutputResult {
    pub code: c_int,
    pub pop: bool,
    pub set_offset: bool,
    pub offset: u32,
    pub close_wait: bool,
    pub send_wait: bool,
    pub warn: c_int,
    pub requested: usize,
}

fn classify(hooks: &OutputHooks) -> c_int {
    let error = Error::last_os_error().raw_os_error().unwrap_or(0);
    // SAFETY: the caller's kernel_nobufs flag.
    unsafe { crate::swr_v1_socket_catch_error(error, hooks.kernel_nobufs) }
}

/// `Socket::handle_send`: send what is left of the front data chunk, `length`
/// bytes at `data` of which `offset` are already sent.
///
/// # Safety
/// `hooks` is valid for this call and `data` denotes `length` readable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_handle_send(
    hooks: *const OutputHooks,
    data: *const u8,
    length: u32,
    offset: u32,
) -> OutputResult {
    // SAFETY: the caller lends its hooks for this call.
    let hooks = unsafe { &*hooks };
    let mut result = OutputResult::default();
    let rest = length.wrapping_sub(offset);
    if rest == 0 {
        result.pop = true;
        return result;
    }
    // SAFETY: the unsent tail of the caller's chunk.
    let sent = unsafe {
        (hooks.send)(
            hooks.socket,
            data.wrapping_add(offset as usize).cast(),
            rest as usize,
        )
    };
    if sent < 0 {
        match classify(hooks) {
            ERROR => result.warn = 1,
            CLOSE => (result.close_wait, result.code) = (true, ERR),
            WAIT => (result.send_wait, result.code) = (true, ERR),
            _ => {}
        }
        return result;
    }
    let sent = sent.cast_unsigned();
    if sent == rest as usize {
        result.pop = true;
        return result;
    }
    #[expect(
        clippy::cast_possible_truncation,
        reason = "upstream adds ssize_t to uint32_t offset"
    )]
    let advanced = offset.wrapping_add(sent as u32);
    (result.set_offset, result.offset) = (true, advanced);
    if sent < rest as usize {
        (result.send_wait, result.code) = (true, ERR);
    }
    result
}

/// `Socket::handle_sendfile` before its send: cork once, when more than `cork_min`
/// bytes of `[begin, end)` remain. `*corked` is the request's 0 unset / 1 / -1.
///
/// # Safety
/// `hooks` is valid for this call and `corked` is the request's writable field.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_sendfile_cork(
    hooks: *const OutputHooks,
    corked: *mut i8,
    begin: libc::off_t,
    end: libc::off_t,
    cork_min: libc::off_t,
) {
    // SAFETY: the caller lends its hooks and request field for this call.
    let (hooks, corked) = (unsafe { &*hooks }, unsafe { &mut *corked });
    if *corked == 0 {
        // SAFETY: the caller's socket.
        *corked = if end - begin > cork_min && unsafe { (hooks.cork)(hooks.socket) } {
            1
        } else {
            -1
        };
    }
}

/// `Socket::handle_sendfile` after native code sent `requested` bytes with result
/// `sent`, leaving the request at `[begin, end)`: classify a failure, record the
/// send time, and uncork and pop once the request is done.
///
/// # Safety
/// `hooks` is valid for this call and `corked` is the request's writable field.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_sendfile_sent(
    hooks: *const OutputHooks,
    sent: isize,
    requested: usize,
    corked: *mut i8,
    begin: libc::off_t,
    end: libc::off_t,
) -> OutputResult {
    // SAFETY: the caller lends its hooks and request field for this call.
    let (hooks, corked) = (unsafe { &*hooks }, unsafe { &mut *corked });
    let result = OutputResult::default();
    if sent <= 0 {
        match classify(hooks) {
            ERROR => {
                return OutputResult {
                    warn: 2,
                    requested,
                    pop: true,
                    ..result
                };
            }
            CLOSE => {
                return OutputResult {
                    code: ERR,
                    close_wait: true,
                    ..result
                };
            }
            WAIT => {
                return OutputResult {
                    code: ERR,
                    send_wait: true,
                    ..result
                };
            }
            _ => {}
        }
    } else {
        // SAFETY: the caller's socket.
        unsafe { (hooks.sent)(hooks.socket) };
    }
    if begin != end {
        return result;
    }
    if *corked == 1 {
        // SAFETY: the caller's socket.
        unsafe { (hooks.uncork)(hooks.socket) };
        *corked = 0;
    }
    OutputResult {
        pop: true,
        ..result
    }
}

/// `Socket::sendfile_async`: `prepare` makes the request and checks its range
/// (false fails the call, discarding it); then `buffer` makes the output buffer
/// if there is none and `enqueue` hands the request to it.
///
/// # Safety
/// Each callback is valid for `socket`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_sendfile_async(
    socket: *mut c_void,
    prepare: unsafe extern "C" fn(socket: *mut c_void) -> bool,
    buffer: unsafe extern "C" fn(socket: *mut c_void),
    enqueue: unsafe extern "C" fn(socket: *mut c_void),
) -> c_int {
    // SAFETY: the caller's request construction and check.
    if !unsafe { prepare(socket) } {
        return ERR;
    }
    // SAFETY: the caller's buffer and queue effects, in upstream's order.
    unsafe { buffer(socket) };
    // SAFETY: as above.
    unsafe { enqueue(socket) };
    OK
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    #[derive(Default)]
    struct Fake {
        sends: Vec<usize>,
        each: isize,
        errno: c_int,
        corks: u32,
        uncorks: u32,
        sent: u32,
        cork_ok: bool,
    }

    thread_local! {
        static FAKE: RefCell<Fake> = RefCell::new(Fake::default());
    }

    fn set_errno(value: c_int) {
        #[cfg(target_os = "linux")]
        // SAFETY: this thread's errno slot.
        unsafe {
            *libc::__errno_location() = value;
        }
        #[cfg(not(target_os = "linux"))]
        // SAFETY: this thread's errno slot.
        unsafe {
            *libc::__error() = value;
        }
    }

    unsafe extern "C" fn send(_: *mut c_void, _: *const c_void, length: usize) -> isize {
        FAKE.with(|fake| {
            let mut fake = fake.borrow_mut();
            fake.sends.push(length);
            set_errno(fake.errno);
            if fake.each < 0 {
                -1
            } else {
                fake.each.min(length.cast_signed())
            }
        })
    }
    unsafe extern "C" fn cork(_: *mut c_void) -> bool {
        FAKE.with(|fake| {
            fake.borrow_mut().corks += 1;
            fake.borrow().cork_ok
        })
    }
    unsafe extern "C" fn uncork(_: *mut c_void) {
        FAKE.with(|fake| fake.borrow_mut().uncorks += 1);
    }
    unsafe extern "C" fn sent(_: *mut c_void) {
        FAKE.with(|fake| fake.borrow_mut().sent += 1);
    }

    fn hooks(socket: *mut c_void, nobufs: &mut bool) -> OutputHooks {
        OutputHooks {
            socket,
            kernel_nobufs: nobufs,
            send,
            cork,
            uncork,
            sent,
        }
    }

    fn reset(each: isize, errno: c_int, cork_ok: bool) {
        FAKE.with(|fake| {
            *fake.borrow_mut() = Fake {
                each,
                errno,
                cork_ok,
                ..Fake::default()
            }
        });
    }

    #[test]
    fn handle_send_rules() {
        let mut nobufs = false;
        let hooks = hooks(std::ptr::null_mut(), &mut nobufs);
        let data = [0_u8; 10];
        let run = |each, errno, length, offset| {
            reset(each, errno, false);
            // SAFETY: local hooks and data.
            unsafe { swr_v1_socket_handle_send(&raw const hooks, data.as_ptr(), length, offset) }
        };
        assert_eq!(
            run(5, 0, 10, 10),
            OutputResult {
                pop: true,
                ..Default::default()
            },
            "nothing left"
        );
        assert_eq!(
            run(5, 0, 10, 5),
            OutputResult {
                pop: true,
                ..Default::default()
            },
            "the rest went"
        );
        assert_eq!(
            run(2, 0, 10, 5),
            OutputResult {
                code: ERR,
                set_offset: true,
                offset: 7,
                send_wait: true,
                ..Default::default()
            },
            "short write"
        );
        assert_eq!(
            run(-1, libc::EAGAIN, 10, 0),
            OutputResult {
                code: ERR,
                send_wait: true,
                ..Default::default()
            }
        );
        assert_eq!(
            run(-1, libc::EPIPE, 10, 0),
            OutputResult {
                code: ERR,
                close_wait: true,
                ..Default::default()
            }
        );
        assert_eq!(
            run(-1, libc::EINVAL, 10, 0),
            OutputResult {
                warn: 1,
                ..Default::default()
            }
        );
    }

    #[test]
    fn handle_sendfile_rules() {
        let mut nobufs = false;
        let hooks = hooks(std::ptr::null_mut(), &mut nobufs);
        let mut corked: i8 = 0;
        reset(0, 0, true);
        // 100,000 bytes from 0 corks once; a partial send keeps the request.
        // SAFETY: local hooks and request field.
        unsafe {
            swr_v1_socket_sendfile_cork(&raw const hooks, &raw mut corked, 0, 100_000, 65_536);
        }
        // SAFETY: as above.
        unsafe {
            swr_v1_socket_sendfile_cork(&raw const hooks, &raw mut corked, 65_536, 100_000, 65_536);
        }
        // SAFETY: as above.
        let partial = unsafe {
            swr_v1_socket_sendfile_sent(
                &raw const hooks,
                65_536,
                65_536,
                &raw mut corked,
                65_536,
                100_000,
            )
        };
        assert_eq!((partial, corked), (OutputResult::default(), 1));
        // SAFETY: as above.
        let done = unsafe {
            swr_v1_socket_sendfile_sent(
                &raw const hooks,
                34_464,
                34_464,
                &raw mut corked,
                100_000,
                100_000,
            )
        };
        assert_eq!(
            (done, corked),
            (
                OutputResult {
                    pop: true,
                    ..Default::default()
                },
                0
            )
        );
        FAKE.with(|fake| {
            let fake = fake.borrow();
            assert_eq!((fake.corks, fake.uncorks, fake.sent), (1, 1, 2));
        });

        // A small file never corks; EAGAIN waits; an error warns and pops.
        let mut corked: i8 = 0;
        reset(0, 0, true);
        // SAFETY: as above.
        unsafe { swr_v1_socket_sendfile_cork(&raw const hooks, &raw mut corked, 0, 10, 65_536) };
        assert_eq!(corked, -1);
        set_errno(libc::EAGAIN);
        // SAFETY: as above.
        let waited = unsafe {
            swr_v1_socket_sendfile_sent(&raw const hooks, -1, 10, &raw mut corked, 0, 10)
        };
        assert_eq!(
            waited,
            OutputResult {
                code: ERR,
                send_wait: true,
                ..Default::default()
            }
        );
        set_errno(libc::EINVAL);
        // SAFETY: as above.
        let failed = unsafe {
            swr_v1_socket_sendfile_sent(&raw const hooks, -1, 10, &raw mut corked, 0, 10)
        };
        assert_eq!(
            failed,
            OutputResult {
                pop: true,
                warn: 2,
                requested: 10,
                ..Default::default()
            }
        );
        FAKE.with(|fake| assert_eq!(fake.borrow().corks, 0));
    }

    #[test]
    fn sendfile_async_order() {
        unsafe extern "C" fn accept(socket: *mut c_void) -> bool {
            // SAFETY: the test's log.
            unsafe { (*socket.cast::<Vec<u8>>()).push(b'p') };
            true
        }
        unsafe extern "C" fn refuse(socket: *mut c_void) -> bool {
            // SAFETY: the test's log.
            unsafe { (*socket.cast::<Vec<u8>>()).push(b'p') };
            false
        }
        unsafe extern "C" fn buffer(socket: *mut c_void) {
            // SAFETY: the test's log.
            unsafe { (*socket.cast::<Vec<u8>>()).push(b'b') };
        }
        unsafe extern "C" fn enqueue(socket: *mut c_void) {
            // SAFETY: the test's log.
            unsafe { (*socket.cast::<Vec<u8>>()).push(b'e') };
        }
        let mut log: Vec<u8> = Vec::new();
        let socket = (&raw mut log).cast();
        // SAFETY: the callbacks write to the local log.
        assert_eq!(
            unsafe { swr_v1_socket_sendfile_async(socket, accept, buffer, enqueue) },
            OK
        );
        // SAFETY: as above.
        assert_eq!(
            unsafe { swr_v1_socket_sendfile_async(socket, refuse, buffer, enqueue) },
            ERR
        );
        assert_eq!(log, b"pbep");
    }
}
