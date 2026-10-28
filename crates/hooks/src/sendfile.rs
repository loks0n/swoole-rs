//! The coroutine socket's `sendfile` loop as a whole operation: chunks of at most
//! `SW_SENDFILE_CHUNK_SIZE` until the range is sent, waiting for the socket when a
//! send would block. Native code opens and measures the file, keeps the timer and
//! writes the errors, and passes the send and the wait in [`SendfileOps`].
use core::ffi::{c_int, c_void};

/// `SW_SENDFILE_CHUNK_SIZE`.
const CHUNK: usize = 65536;
/// Outcomes besides 0 (all sent).
const ZERO: c_int = 1;
const FAILED: c_int = 2;
const WAIT_FAILED: c_int = 3;

#[repr(C)]
pub struct SendfileOps {
    pub context: *mut c_void,
    /// `network::Socket::sendfile` of `length` bytes from `*offset`, which it advances;
    /// sets errno when it fails.
    pub send: unsafe extern "C" fn(*mut c_void, *mut libc::off_t, usize) -> isize,
    /// `timer.start()` and the write wait.
    pub wait: unsafe extern "C" fn(*mut c_void) -> bool,
}

/// Sends `[*offset, end)`. Returns 0 once it all went, 1 when a send returned
/// zero, 2 when one failed other than with `EAGAIN` (errno left set) and 3 when
/// the wait failed.
///
/// # Safety
/// `ops` is live for the call and `offset` is writable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_sendfile(
    ops: *const SendfileOps,
    offset: *mut libc::off_t,
    end: usize,
) -> c_int {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    loop {
        // SAFETY: the caller's offset, which only `send` advances.
        let at = usize::try_from(unsafe { *offset }).unwrap_or(usize::MAX);
        if at >= end {
            return 0;
        }
        // SAFETY: the live socket's sendfile of the next chunk.
        let sent = unsafe { (ops.send)(ops.context, offset, (end - at).min(CHUNK)) };
        if sent > 0 {
            continue;
        }
        if sent == 0 {
            return ZERO;
        }
        if std::io::Error::last_os_error().raw_os_error() != Some(libc::EAGAIN) {
            return FAILED;
        }
        // SAFETY: the live socket's timer and wait.
        if !unsafe { (ops.wait)(ops.context) } {
            return WAIT_FAILED;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    thread_local! {
        /// Each send's result: bytes sent, or `-errno`.
        static SENDS: RefCell<Vec<isize>> = const { RefCell::new(Vec::new()) };
        static LOG: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
        static WAIT: RefCell<bool> = const { RefCell::new(true) };
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

    unsafe extern "C" fn send(_: *mut c_void, offset: *mut libc::off_t, length: usize) -> isize {
        LOG.with(|log| log.borrow_mut().push(format!("send {length}")));
        let result = SENDS.with(|sends| sends.borrow_mut().remove(0));
        if result < 0 {
            set_errno(c_int::try_from(-result).unwrap());
            return -1;
        }
        // SAFETY: the test's offset.
        unsafe { *offset += libc::off_t::try_from(result).unwrap() };
        result
    }
    unsafe extern "C" fn wait(_: *mut c_void) -> bool {
        LOG.with(|log| log.borrow_mut().push("wait".into()));
        WAIT.with(|wait| *wait.borrow())
    }

    fn run(
        sends: &[isize],
        wait_ok: bool,
        start: libc::off_t,
        end: usize,
    ) -> (c_int, libc::off_t, Vec<String>) {
        SENDS.with(|s| *s.borrow_mut() = sends.to_vec());
        LOG.with(|log| log.borrow_mut().clear());
        WAIT.with(|wait| *wait.borrow_mut() = wait_ok);
        let ops = SendfileOps {
            context: std::ptr::null_mut(),
            send,
            wait,
        };
        let mut offset = start;
        // SAFETY: local table and offset.
        let outcome = unsafe { swr_v1_hook_sendfile(&raw const ops, &raw mut offset, end) };
        (outcome, offset, LOG.with(|log| log.borrow().clone()))
    }

    #[test]
    fn chunks_waits_and_failures() {
        let eagain = -isize::try_from(libc::EAGAIN).unwrap();
        // 100,000 bytes from 10: a full chunk, a would-block wait, then the rest.
        let (outcome, offset, log) = run(&[65_536, eagain, 34_454], true, 10, 100_000);
        assert_eq!((outcome, offset), (0, 100_000));
        assert_eq!(log, ["send 65536", "send 34454", "wait", "send 34454"]);
        assert_eq!(run(&[], true, 5, 5).0, 0, "nothing to send");
        assert_eq!(run(&[0], true, 0, 10).0, ZERO);
        assert_eq!(
            run(&[-isize::try_from(libc::EPIPE).unwrap()], true, 0, 10).0,
            FAILED
        );
        assert_eq!(run(&[eagain], false, 0, 10).0, WAIT_FAILED);
    }
}
