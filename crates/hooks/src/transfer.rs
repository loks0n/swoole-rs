//! The coroutine socket's transfers as whole operations: one call retried while the
//! socket would block (`recv`, `send`, `read`, `write`, `readv`, `writev`,
//! `recvmsg`, `sendmsg`, `recvfrom`, `sendto`), and the all-or-nothing transfer of
//! `recv_all`/`send_all`. Native code keeps the availability check, the timer, the
//! coroutine wait and the `network::Socket` call itself, and passes them in
//! `TransferOps`. A C++ exception never crosses these frames: native code catches
//! it in its callback, stops the loop and rethrows after this returns.
use crate::vector::Barrier;
use core::ffi::c_void;

/// One transfer's effects. Every callback gets `context`.
#[repr(C)]
pub struct TransferOps {
    pub context: *mut c_void,
    /// Retry at once when the call fails with `EINTR` (the datagram calls).
    pub retry_interrupted: bool,
    /// The `network::Socket` (or syscall) transfer of `length` bytes at `buffer`;
    /// sets errno when it fails.
    pub call: unsafe extern "C" fn(*mut c_void, *mut u8, usize) -> isize,
    /// `catch_read_error`/`catch_write_error(errno) == SW_WAIT`.
    pub would_block: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `timer.start()`.
    pub start: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Waits for the socket, with `barrier` installed when given. `buffer`, when
    /// not null, is the caller's buffer slot, which a write's wait may move to
    /// the socket's write buffer (`wait_event`'s copy).
    pub wait: unsafe extern "C" fn(*mut c_void, Option<Barrier>, *mut c_void, *mut *mut u8) -> bool,
    /// `check_return_value`.
    pub check: unsafe extern "C" fn(*mut c_void, isize),
    /// `set_err(errno)`.
    pub fail: unsafe extern "C" fn(*mut c_void),
}

impl TransferOps {
    fn call(&self, buffer: *mut u8, length: usize) -> isize {
        // SAFETY: the native transfer for the live socket, over the caller's buffer.
        unsafe { (self.call)(self.context, buffer, length) }
    }

    fn would_block(&self) -> bool {
        // SAFETY: classifies errno on the live socket.
        unsafe { (self.would_block)(self.context) }
    }

    fn start(&self) -> bool {
        // SAFETY: starts the live socket's timer.
        unsafe { (self.start)(self.context) }
    }

    /// Waits for the socket; `state` and `buffer` outlive the wait (see `wait`).
    fn wait(&self, barrier: Option<Barrier>, state: *mut c_void, buffer: *mut *mut u8) -> bool {
        // SAFETY: a native wait on the live socket; the caller keeps `state` and
        // `buffer` alive across it, and a moved buffer holds the same bytes.
        unsafe { (self.wait)(self.context, barrier, state, buffer) }
    }
}

fn interrupted() -> bool {
    std::io::Error::last_os_error().raw_os_error() == Some(libc::EINTR)
}

/// One transfer, retried while the socket would block: classify, start the timer,
/// wait, call again. Returns the last call's result after `check_return_value`.
///
/// # Safety
/// `ops` is live for the call; `buffer` holds `length` bytes for the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_io(
    ops: *const TransferOps,
    buffer: *mut u8,
    length: usize,
) -> isize {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let mut buffer = buffer;
    let mut result = ops.call(buffer, length);
    while result < 0 {
        if ops.retry_interrupted && interrupted() {
            result = ops.call(buffer, length);
            continue;
        }
        if !ops.would_block()
            || !ops.start()
            || !ops.wait(None, core::ptr::null_mut(), &raw mut buffer)
        {
            break;
        }
        result = ops.call(buffer, length);
    }
    // SAFETY: a native effect on the live socket.
    unsafe { (ops.check)(ops.context, result) };
    result
}

struct All<'a> {
    ops: &'a TransferOps,
    buffer: *mut u8,
    length: usize,
    total: usize,
    result: isize,
}

/// The barrier's retry for `transfer_all`: transfer the rest; keep waiting while it
/// would block or is still short.
unsafe extern "C" fn rest(state: *mut c_void) -> bool {
    // SAFETY: `state` is the All that swr_v1_hook_io_all lent to `wait`.
    let all = unsafe { &mut *state.cast::<All>() };
    all.result = all
        .ops
        .call(all.buffer.wrapping_add(all.total), all.length - all.total);
    if all.result > 0 {
        all.total += all.result.unsigned_abs();
    }
    all.result < 0 && all.ops.would_block() || all.result > 0 && all.total < all.length
}

/// `recv_all`/`send_all`: `length` bytes, or fewer at EOF, error or timeout. Returns
/// the bytes transferred, -1 when none were, or the first call's result when it
/// finished at once or failed outright.
///
/// # Safety
/// `ops` is live for the call; `buffer` holds `length` bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_io_all(
    ops: *const TransferOps,
    buffer: *mut u8,
    length: usize,
) -> isize {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let first = ops.call(buffer, length);
    if first == 0 || first.unsigned_abs() == length && first > 0 {
        return first;
    }
    if first < 0 && !ops.would_block() {
        // SAFETY: a native effect on the live socket.
        unsafe { (ops.fail)(ops.context) };
        return first;
    }
    let mut all = All {
        ops,
        buffer,
        length,
        total: if first > 0 { first.unsigned_abs() } else { 0 },
        result: -1,
    };
    // `all` outlives the wait, which calls `rest` with it.
    if ops.start() && ops.wait(Some(rest), (&raw mut all).cast(), core::ptr::null_mut()) {
        // SAFETY: a native effect on the live socket.
        unsafe { (ops.check)(ops.context, all.result) };
    }
    if all.result < 0 && all.total == 0 {
        -1
    } else {
        all.total.cast_signed()
    }
}

#[cfg(test)]
#[expect(
    clippy::cast_possible_wrap,
    clippy::cast_sign_loss,
    reason = "the test socket drives the native integer interface with small lengths"
)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    /// A socket whose calls return scripted results (negative: -errno) and moves bytes.
    struct Fake {
        results: VecDeque<isize>,
        moved: usize,
        events: Vec<String>,
        wakes: bool,
    }

    unsafe fn fake<'a>(context: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *context.cast::<Fake>() }
    }

    unsafe extern "C" fn call(c: *mut c_void, _: *mut u8, length: usize) -> isize {
        let this = unsafe { fake(c) };
        let result = this.results.pop_front().unwrap_or(0);
        if result < 0 {
            set_errno(i32::try_from(-result).unwrap());
            return -1;
        }
        let moved = (result as usize).min(length);
        this.moved += moved;
        moved as isize
    }

    fn set_errno(error: i32) {
        #[cfg(target_os = "linux")]
        unsafe {
            *libc::__errno_location() = error;
        }
        #[cfg(target_vendor = "apple")]
        unsafe {
            *libc::__error() = error;
        }
    }

    unsafe extern "C" fn would_block(_: *mut c_void) -> bool {
        std::io::Error::last_os_error().raw_os_error() == Some(libc::EAGAIN)
    }
    unsafe extern "C" fn start(c: *mut c_void) -> bool {
        unsafe { fake(c) }.events.push("start".into());
        true
    }
    unsafe extern "C" fn wait(
        c: *mut c_void,
        barrier: Option<Barrier>,
        state: *mut c_void,
        _: *mut *mut u8,
    ) -> bool {
        let this = unsafe { fake(c) };
        this.events.push("wait".into());
        if !this.wakes {
            return false;
        }
        if let Some(barrier) = barrier {
            while unsafe { barrier(state) } {
                unsafe { fake(c) }.events.push("again".into());
            }
        }
        true
    }
    unsafe extern "C" fn check(c: *mut c_void, result: isize) {
        unsafe { fake(c) }.events.push(format!("check:{result}"));
    }
    unsafe extern "C" fn fail(c: *mut c_void) {
        unsafe { fake(c) }.events.push("fail".into());
    }

    fn run(
        all: bool,
        eintr: bool,
        results: &[isize],
        length: usize,
        wakes: bool,
    ) -> (isize, Vec<String>) {
        let mut fake = Fake {
            results: results.iter().copied().collect(),
            moved: 0,
            events: Vec::new(),
            wakes,
        };
        let ops = TransferOps {
            context: (&raw mut fake).cast(),
            retry_interrupted: eintr,
            call,
            would_block,
            start,
            wait,
            check,
            fail,
        };
        let mut buffer = vec![0u8; length];
        let result = unsafe {
            if all {
                swr_v1_hook_io_all(&raw const ops, buffer.as_mut_ptr(), length)
            } else {
                swr_v1_hook_io(&raw const ops, buffer.as_mut_ptr(), length)
            }
        };
        (result, fake.events)
    }

    const EAGAIN: isize = -(libc::EAGAIN as isize);
    const EINTR: isize = -(libc::EINTR as isize);
    const EIO: isize = -(libc::EIO as isize);

    #[test]
    fn one_transfer_waits_while_it_would_block() {
        assert_eq!(
            run(false, false, &[5], 8, true),
            (5, vec!["check:5".into()])
        );
        assert_eq!(
            run(false, false, &[EAGAIN, 3], 8, true),
            (3, vec!["start".into(), "wait".into(), "check:3".into()])
        );
        assert_eq!(
            run(false, false, &[EIO], 8, true),
            (-1, vec!["check:-1".into()])
        );
        assert_eq!(
            run(false, false, &[EAGAIN], 8, false),
            (-1, vec!["start".into(), "wait".into(), "check:-1".into()])
        );
    }

    #[test]
    fn datagrams_retry_interrupts_at_once() {
        assert_eq!(
            run(false, true, &[EINTR, 4], 8, true),
            (4, vec!["check:4".into()])
        );
        assert_eq!(
            run(false, false, &[EINTR], 8, true),
            (-1, vec!["check:-1".into()])
        );
    }

    #[test]
    fn all_or_nothing_accumulates_through_the_barrier() {
        assert_eq!(run(true, false, &[8], 8, true), (8, vec![]));
        assert_eq!(run(true, false, &[0], 8, true), (0, vec![]));
        assert_eq!(run(true, false, &[EIO], 8, true), (-1, vec!["fail".into()]));
        assert_eq!(
            run(true, false, &[2, EAGAIN, 3, 3], 8, true),
            (
                8,
                vec![
                    "start".into(),
                    "wait".into(),
                    "again".into(),
                    "again".into(),
                    "check:3".into()
                ]
            )
        );
        assert_eq!(
            run(true, false, &[2, 0], 8, true),
            (2, vec!["start".into(), "wait".into(), "check:0".into()])
        );
        assert_eq!(
            run(true, false, &[EAGAIN], 8, false),
            (-1, vec!["start".into(), "wait".into()])
        );
    }
}
