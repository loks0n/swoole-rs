//! Source-local autoload waiter queue. Tokens remain native stack/context custody.
use std::collections::VecDeque;

pub struct AutoloadQueue {
    owner: usize,
    waiters: VecDeque<usize>,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_autoload_new() -> *mut AutoloadQueue {
    Box::into_raw(Box::new(AutoloadQueue {
        owner: 0,
        waiters: VecDeque::new(),
    }))
}

/// # Safety
/// `queue` is a live exclusive handle; token referents are never accessed here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_push(
    queue: *mut AutoloadQueue,
    token: usize,
) {
    unsafe { &mut *queue }.waiters.push_back(token);
}

/// # Safety
/// `queue` is live and exclusive; `token` is writable and does not alias it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_pop(
    queue: *mut AutoloadQueue,
    token: *mut usize,
) -> u8 {
    match unsafe { &mut *queue }.waiters.pop_front() {
        Some(value) => {
            unsafe { *token = value };
            1
        }
        None => 0,
    }
}

/// # Safety
/// Consume the owned handle once. Only metadata drops; no native token cleanup.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_drop(queue: *mut AutoloadQueue) {
    unsafe { drop(Box::from_raw(queue)) };
}

/// Scalar lookup/recursion/owner-vs-waiter policy. No classloader or Zend pointer
/// enters Rust, and no callback/native runtime executes within this function.
/// # Safety
/// State is exclusive writable native stack POD, initially zero; observations
/// belong only to the previously requested native fact.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_policy(
    stage: *mut u32,
    observation: u8,
) -> u32 {
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        return match current {
            0 => 1,
            1 if observation == 0 => {
                *stage = 99;
                2
            }
            1 => 3,
            2 if observation == 0 => 4,
            2 => continue,
            3 => 5,
            4 if observation == 0 => {
                *stage = 99;
                8
            }
            4 => 6,
            5 => {
                *stage = 99;
                if observation != 0 { 0 } else { 7 }
            }
            _ => {
                *stage = 99;
                0
            }
        };
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_autoload_try_new() -> *mut AutoloadQueue {
    crate::allocation::try_owned(AutoloadQueue {
        owner: 0,
        waiters: VecDeque::new(),
    })
}
/// # Safety
/// Handle is live/exclusive. Failure publishes no new waiter; no referent is read.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_try_push(
    queue: *mut AutoloadQueue,
    token: usize,
) -> u8 {
    let tokens = &mut unsafe { &mut *queue }.waiters;
    if tokens.try_reserve(1).is_err() {
        return 0;
    }
    tokens.push_back(token);
    1
}

/// Own the autoload owner identity and waiter FIFO together. The integer is an
/// opaque Native identity only; Rust never reads its referent or calls Native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_autoload_owner_try_new(owner: usize) -> *mut AutoloadQueue {
    crate::allocation::try_owned(AutoloadQueue {
        owner,
        waiters: VecDeque::new(),
    })
}
/// # Safety
/// Queue is live and exclusively observed for this call. Owner is an opaque
/// identity token; no borrow survives a Native classloader/yield/resume effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_autoload_is_owner(
    queue: *const AutoloadQueue,
    owner: usize,
) -> u8 {
    u8::from(unsafe { &*queue }.owner == owner)
}
#[cfg(test)]
mod owner_tests {
    use super::*;
    #[test]
    fn owner_and_fifo_are_one_opaque_custody() {
        let queue = swr_v1_phpcoroutines_autoload_owner_try_new(73);
        assert!(!queue.is_null());
        unsafe {
            assert_eq!(swr_v1_phpcoroutines_autoload_is_owner(queue, 73), 1);
            assert_eq!(swr_v1_phpcoroutines_autoload_is_owner(queue, 74), 0);
            for token in [0, 17, 0, usize::MAX] {
                assert_eq!(swr_v1_phpcoroutines_autoload_try_push(queue, token), 1);
            }
            let mut result = 123;
            for token in [0, 17, 0, usize::MAX] {
                assert_eq!(swr_v1_phpcoroutines_autoload_pop(queue, &mut result), 1);
                assert_eq!(result, token);
                assert_eq!(swr_v1_phpcoroutines_autoload_is_owner(queue, 73), 1);
            }
            assert_eq!(swr_v1_phpcoroutines_autoload_pop(queue, &mut result), 0);
            swr_v1_phpcoroutines_autoload_drop(queue);
        }
    }
}
