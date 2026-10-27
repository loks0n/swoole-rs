//! `swoole_coroutine_flock`: `flock(2)` as hooked inside a coroutine. A blocking
//! exclusive or shared lock becomes non-blocking attempts with `System::sleep` between
//! them, backing off from `initial` to `maximum` seconds; unlocking, `LOCK_NB` and
//! calls outside a coroutine go straight to flock. Native code keeps raising EINVAL.
use crate::sleep::CoroutineSleep;
use crate::swr_v1_hook_backoff;

/// What the hooked flock returns.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct FlockOutcome {
    /// flock's result: 0 or -1 (errno is flock's, or the cancelled sleep's).
    pub result: i32,
    /// The operation is none of `LOCK_EX`, `LOCK_SH`, `LOCK_UN`: native sets EINVAL.
    pub invalid: bool,
}

fn flock(fd: i32, operation: i32) -> i32 {
    // SAFETY: flock has no memory preconditions.
    unsafe { libc::flock(fd, operation) }
}

/// Locks `fd` like `flock(fd, operation)`, yielding through `coroutine_sleep` while
/// another holder has it. `coroutine_sleep` is null outside a coroutine.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_coroutine_flock(
    fd: i32,
    operation: i32,
    coroutine_sleep: Option<CoroutineSleep>,
    initial: f64,
    maximum: f64,
) -> FlockOutcome {
    let done = |result| FlockOutcome {
        result,
        invalid: false,
    };
    let Some(sleep) = coroutine_sleep.filter(|_| operation & libc::LOCK_NB == 0) else {
        return done(flock(fd, operation));
    };
    if operation == libc::LOCK_UN {
        return done(flock(fd, libc::LOCK_UN));
    }
    if operation != libc::LOCK_EX && operation != libc::LOCK_SH {
        return FlockOutcome {
            result: -1,
            invalid: true,
        };
    }
    let mut delay = initial;
    loop {
        match flock(fd, operation | libc::LOCK_NB) {
            0 => return done(0),
            -1 if std::io::Error::last_os_error().raw_os_error() == Some(libc::EWOULDBLOCK) => {}
            _ => return done(-1),
        }
        // SAFETY: native passes System::sleep, valid inside the current coroutine.
        if unsafe { sleep(delay) } != 0 {
            return done(-1);
        }
        delay = swr_v1_hook_backoff(delay, initial, maximum);
    }
}

#[cfg(test)]
mod tests {
    use super::{FlockOutcome, swr_v1_hook_coroutine_flock};
    use std::cell::RefCell;
    use std::os::fd::AsRawFd;

    thread_local! {
        /// The delays slept, and the descriptor to unlock on the second sleep.
        static SLEPT: RefCell<(Vec<f64>, i32)> = const { RefCell::new((Vec::new(), -1)) };
    }
    unsafe extern "C" fn release_on_second(seconds: f64) -> i32 {
        SLEPT.with_borrow_mut(|(slept, holder)| {
            slept.push(seconds);
            if slept.len() == 2 {
                unsafe { libc::flock(*holder, libc::LOCK_UN) };
            }
        });
        0
    }
    unsafe extern "C" fn cancelled(_: f64) -> i32 {
        -1
    }

    fn lock(fd: i32, operation: i32, sleep: Option<super::CoroutineSleep>) -> FlockOutcome {
        swr_v1_hook_coroutine_flock(fd, operation, sleep, 0.001, 0.1)
    }

    #[test]
    fn waits_for_the_holder_backing_off() {
        let path = std::env::temp_dir().join(format!("swr-flock-{}", std::process::id()));
        let holder = std::fs::File::create(&path).unwrap();
        let waiter = std::fs::File::open(&path).unwrap();
        let (holder, waiter) = (holder.as_raw_fd(), waiter.as_raw_fd());
        let ok = FlockOutcome::default();

        assert_eq!(lock(holder, libc::LOCK_EX, Some(release_on_second)), ok);
        SLEPT.with_borrow_mut(|state| state.1 = holder);
        assert_eq!(lock(waiter, libc::LOCK_SH, Some(release_on_second)), ok);
        assert_eq!(SLEPT.with_borrow(|state| state.0.clone()), [0.001, 0.002]);

        assert_eq!(
            lock(holder, libc::LOCK_EX | libc::LOCK_NB, Some(cancelled)).result,
            -1
        );
        assert_eq!(lock(holder, libc::LOCK_EX, Some(cancelled)).result, -1);
        assert_eq!(lock(waiter, libc::LOCK_UN, Some(cancelled)), ok);
        assert_eq!(lock(holder, libc::LOCK_EX, Some(cancelled)), ok);
        assert_eq!(lock(holder, libc::LOCK_UN, None), ok);

        let invalid = lock(holder, libc::LOCK_EX | libc::LOCK_SH, Some(cancelled));
        assert_eq!((invalid.result, invalid.invalid), (-1, true));
        assert_eq!(lock(-1, libc::LOCK_EX, Some(cancelled)).result, -1);
        std::fs::remove_file(path).unwrap();
    }
}
