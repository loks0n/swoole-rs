//! `Socket::readv_all` and `Socket::writev_all` of the coroutine socket: transfer a
//! whole `IOVector`, waiting for the socket while it would block. Native code keeps
//! the availability check, the timer, the `IOVector` and the coroutine wait, and
//! passes them in `VectorOps`.
use core::ffi::c_void;

/// Retries the transfer once the socket is ready; true to keep waiting.
pub type Barrier = unsafe extern "C" fn(*mut c_void) -> bool;

/// The socket's effects for one direction. Every callback gets `context`.
#[repr(C)]
pub struct VectorOps {
    pub context: *mut c_void,
    /// `socket->readv`/`writev` of the vector; `first` traces the first call.
    pub transfer: unsafe extern "C" fn(*mut c_void, bool) -> isize,
    /// `catch_read_error`/`catch_write_error(errno) == SW_WAIT`.
    pub would_block: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `IOVector::get_remain_count`.
    pub remaining: unsafe extern "C" fn(*mut c_void) -> usize,
    /// `set_err(errno)`.
    pub fail: unsafe extern "C" fn(*mut c_void),
    /// Installs `barrier` (with its state) and runs `timer.start() && wait_event`.
    pub wait: unsafe extern "C" fn(*mut c_void, Barrier, *mut c_void) -> bool,
    /// `check_return_value`.
    pub check: unsafe extern "C" fn(*mut c_void, isize),
}

struct Transfer<'a> {
    ops: &'a VectorOps,
    result: isize,
    total: isize,
}

impl Transfer<'_> {
    fn transfer(&mut self, first: bool) {
        // SAFETY: a native effect on the live socket and vector in `context`.
        self.result = unsafe { (self.ops.transfer)(self.ops.context, first) };
        if self.result > 0 {
            self.total = self.total.wrapping_add(self.result);
        }
    }

    fn would_block(&self) -> bool {
        // SAFETY: reads errno and classifies it on the live socket in `context`.
        unsafe { (self.ops.would_block)(self.ops.context) }
    }

    fn remaining(&self) -> usize {
        // SAFETY: a read of the live vector in `context`.
        unsafe { (self.ops.remaining)(self.ops.context) }
    }
}

/// The barrier's retry: transfer until the vector is done or a call returns <= 0;
/// keep waiting only when the last call would block.
unsafe extern "C" fn retry(state: *mut c_void) -> bool {
    // SAFETY: `state` is the Transfer that swr_v1_hook_vector_all lent to `wait`.
    let transfer = unsafe { &mut *state.cast::<Transfer>() };
    loop {
        transfer.transfer(false);
        if transfer.result <= 0 || transfer.remaining() == 0 {
            break;
        }
    }
    transfer.result < 0 && transfer.would_block()
}

/// `readv_all`/`writev_all` after the availability check and the timer's creation:
/// the bytes transferred, or the first call's result when it finished or failed.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the socket in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_vector_all(ops: *const VectorOps) -> isize {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let mut transfer = Transfer {
        ops,
        result: 0,
        total: 0,
    };
    transfer.transfer(true);
    let first = transfer.result;
    if first < 0 && !transfer.would_block() {
        // SAFETY: a native effect on the live socket.
        unsafe { (ops.fail)(ops.context) };
        return first;
    }
    if first == 0 {
        return first;
    }
    // The iov must not be touched again once complete.
    if transfer.remaining() == 0 {
        return first;
    }
    // SAFETY: `transfer` outlives the wait, which calls `retry` with it.
    if unsafe { (ops.wait)(ops.context, retry, (&raw mut transfer).cast()) } {
        // SAFETY: a native effect on the live socket.
        unsafe { (ops.check)(ops.context, transfer.result) };
    }
    transfer.total
}

#[cfg(test)]
#[expect(
    clippy::cast_possible_wrap,
    clippy::cast_sign_loss,
    reason = "the test vector drives the native integer interface with small lengths"
)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    /// A vector of `remaining` bytes moved by scripted transfer results; a negative
    /// result is -errno, EAGAIN would block.
    struct Fake {
        results: VecDeque<isize>,
        remaining: usize,
        errno: isize,
        events: Vec<String>,
        wakes: bool,
    }

    unsafe fn fake<'a>(context: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *context.cast::<Fake>() }
    }

    unsafe extern "C" fn transfer(context: *mut c_void, _: bool) -> isize {
        let fake = unsafe { fake(context) };
        let result = fake.results.pop_front().unwrap_or(0);
        if result < 0 {
            fake.errno = -result;
            return -1;
        }
        let moved = (result as usize).min(fake.remaining);
        fake.remaining -= moved;
        moved as isize
    }

    unsafe extern "C" fn would_block(context: *mut c_void) -> bool {
        unsafe { fake(context) }.errno == libc::EAGAIN as isize
    }

    unsafe extern "C" fn remaining(context: *mut c_void) -> usize {
        unsafe { fake(context) }.remaining
    }

    unsafe extern "C" fn fail(context: *mut c_void) {
        unsafe { fake(context) }.events.push("fail".into());
    }

    unsafe extern "C" fn wait(context: *mut c_void, barrier: Barrier, state: *mut c_void) -> bool {
        let this = unsafe { fake(context) };
        this.events.push("wait".into());
        if !this.wakes {
            return false;
        }
        while unsafe { barrier(state) } {
            unsafe { fake(context) }.events.push("again".into());
        }
        true
    }

    unsafe extern "C" fn check(context: *mut c_void, result: isize) {
        unsafe { fake(context) }
            .events
            .push(format!("check:{result}"));
    }

    fn run(results: &[isize], remaining: usize, wakes: bool) -> (isize, Vec<String>) {
        let mut fake = Fake {
            results: results.iter().copied().collect(),
            remaining,
            errno: 0,
            events: Vec::new(),
            wakes,
        };
        let ops = VectorOps {
            context: (&raw mut fake).cast(),
            transfer,
            would_block,
            remaining: self::remaining,
            fail,
            wait: self::wait,
            check,
        };
        let result = unsafe { swr_v1_hook_vector_all(&raw const ops) };
        (result, fake.events)
    }

    #[test]
    fn a_complete_first_transfer_returns_without_waiting() {
        assert_eq!(run(&[8], 8, true), (8, vec![]));
    }

    #[test]
    fn a_hard_error_or_eof_returns_the_first_result() {
        assert_eq!(
            run(&[-libc::EIO as isize], 8, true),
            (-1, vec!["fail".into()])
        );
        assert_eq!(run(&[0], 8, true), (0, vec![]));
    }

    #[test]
    fn partial_transfers_wait_and_accumulate() {
        let eagain = -libc::EAGAIN as isize;
        assert_eq!(
            run(&[2, eagain, 3, 3], 8, true),
            (8, vec!["wait".into(), "again".into(), "check:3".into()])
        );
        assert_eq!(
            run(&[eagain, 8], 8, true),
            (8, vec!["wait".into(), "check:8".into()])
        );
        assert_eq!(
            run(&[2, 0], 8, true),
            (2, vec!["wait".into(), "check:0".into()])
        );
        assert_eq!(run(&[2], 8, false), (2, vec!["wait".into()]));
    }
}
