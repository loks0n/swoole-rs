//! Native-compatible synchronization. Callers allocate/free storage outside Rust.
#![deny(unsafe_op_in_unsafe_fn)]
#![allow(clippy::missing_safety_doc)]
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
compile_error!("Rust locks require validated macOS or Linux platform contracts");

use libc::*;
use std::{
    mem::{align_of, size_of},
    ptr,
    sync::atomic::{AtomicI64, AtomicU32, Ordering},
};

// libc 0.2.191 omits these Linux declarations; signatures match pthread.h.
#[cfg(target_os = "linux")]
unsafe extern "C" {
    fn pthread_rwlock_timedrdlock(lock: *mut pthread_rwlock_t, deadline: *const timespec) -> c_int;
    fn pthread_rwlock_timedwrlock(lock: *mut pthread_rwlock_t, deadline: *const timespec) -> c_int;
}

#[repr(C)]
struct Mutex {
    lock: pthread_mutex_t,
    attr: pthread_mutexattr_t,
}
#[repr(C)]
struct RwLock {
    lock: pthread_rwlock_t,
    attr: pthread_rwlockattr_t,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_locks_size(kind: i32) -> usize {
    match kind {
        3 => size_of::<Mutex>(),
        1 => size_of::<RwLock>(),
        #[cfg(target_os = "linux")]
        5 => size_of::<pthread_spinlock_t>(),
        _ => 0,
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_locks_align(kind: i32) -> usize {
    match kind {
        3 => align_of::<Mutex>(),
        1 => align_of::<RwLock>(),
        #[cfg(target_os = "linux")]
        5 => align_of::<pthread_spinlock_t>(),
        _ => 0,
    }
}
fn valid(storage: *mut c_void, kind: i32) -> bool {
    let align = swr_v1_locks_align(kind);
    !storage.is_null() && align != 0 && (storage as usize).is_multiple_of(align)
}
// Failed lock initialization owns an initialized attribute, but not a live lock.
fn init_result(result: c_int, destroy_attr: impl FnOnce()) -> c_int {
    if result != 0 {
        unsafe {
            #[cfg(target_os = "linux")]
            let error = __errno_location();
            #[cfg(target_os = "macos")]
            let error = __error();
            let saved = *error;
            destroy_attr();
            *error = saved;
        }
    }
    result
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_init(storage: *mut c_void, kind: i32, shared: i32) -> i32 {
    if !valid(storage, kind) {
        return EINVAL;
    }
    unsafe {
        match kind {
            3 => {
                let s = storage.cast::<Mutex>();
                let result = pthread_mutexattr_init(ptr::addr_of_mut!((*s).attr));
                if result != 0 {
                    return result;
                }
                let attributes = if shared != 0 {
                    pthread_mutexattr_setpshared(
                        ptr::addr_of_mut!((*s).attr),
                        PTHREAD_PROCESS_SHARED,
                    )
                } else {
                    0
                };
                let result = if attributes != 0 {
                    attributes
                } else {
                    pthread_mutex_init(ptr::addr_of_mut!((*s).lock), ptr::addr_of!((*s).attr))
                };
                init_result(result, || {
                    pthread_mutexattr_destroy(ptr::addr_of_mut!((*s).attr));
                })
            }
            1 => {
                let s = storage.cast::<RwLock>();
                let result = pthread_rwlockattr_init(ptr::addr_of_mut!((*s).attr));
                if result != 0 {
                    return result;
                }
                let attributes = if shared != 0 {
                    pthread_rwlockattr_setpshared(
                        ptr::addr_of_mut!((*s).attr),
                        PTHREAD_PROCESS_SHARED,
                    )
                } else {
                    0
                };
                let result = if attributes != 0 {
                    attributes
                } else {
                    pthread_rwlock_init(ptr::addr_of_mut!((*s).lock), ptr::addr_of!((*s).attr))
                };
                init_result(result, || {
                    pthread_rwlockattr_destroy(ptr::addr_of_mut!((*s).attr));
                })
            }
            #[cfg(target_os = "linux")]
            5 => pthread_spin_init(storage.cast(), shared),
            _ => EINVAL,
        }
    }
}
// Match sw_wait_for's exact attempt/sleep/backoff order, including its final attempt.
unsafe fn poll(mut timeout: i32, mut attempt: impl FnMut() -> i32) -> i32 {
    let mut sleep: i32 = 1;
    while timeout >= 0 {
        if attempt() == 0 {
            return 0;
        }
        unsafe {
            usleep(sleep.wrapping_mul(1000) as u32);
        }
        sleep = sleep.wrapping_mul(2);
        if timeout > 0 && timeout.wrapping_sub(sleep) < 0 {
            sleep = timeout;
            timeout = 0;
        } else {
            timeout = timeout.wrapping_sub(sleep);
        }
    }
    ETIMEDOUT
}
#[cfg(target_os = "linux")]
unsafe fn deadline(millis: i32) -> timespec {
    let mut now = timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    unsafe {
        clock_gettime(CLOCK_REALTIME, &mut now);
    }
    now.tv_sec += (millis / 1000) as time_t;
    now.tv_nsec += (millis % 1000) as c_long * 1_000_000;
    now.tv_sec += (now.tv_nsec / 1_000_000_000) as time_t;
    now.tv_nsec %= 1_000_000_000;
    now
}
// capabilities: bit0 mutex timedlock; bit1 rwlock timed{rd,wr}lock. From native configure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_lock(
    storage: *mut c_void,
    kind: i32,
    operation: i32,
    timeout: i32,
    capabilities: u32,
) -> i32 {
    if !valid(storage, kind) {
        return EINVAL;
    }
    #[cfg(not(target_os = "linux"))]
    let _ = capabilities;
    unsafe {
        match kind {
            3 => {
                let lock = ptr::addr_of_mut!((*storage.cast::<Mutex>()).lock);
                if operation & LOCK_NB != 0 {
                    return pthread_mutex_trylock(lock);
                }
                if timeout > 0 {
                    #[cfg(target_os = "linux")]
                    if capabilities & 1 != 0 {
                        return pthread_mutex_timedlock(lock, &deadline(timeout));
                    }
                    return poll(timeout, || pthread_mutex_trylock(lock));
                }
                pthread_mutex_lock(lock)
            }
            1 => {
                let lock = ptr::addr_of_mut!((*storage.cast::<RwLock>()).lock);
                let read = operation & LOCK_SH != 0;
                if operation & LOCK_NB != 0 {
                    return if read {
                        pthread_rwlock_tryrdlock(lock)
                    } else {
                        pthread_rwlock_trywrlock(lock)
                    };
                }
                if timeout > 0 {
                    #[cfg(target_os = "linux")]
                    if capabilities & 2 != 0 {
                        return if read {
                            pthread_rwlock_timedrdlock(lock, &deadline(timeout))
                        } else {
                            pthread_rwlock_timedwrlock(lock, &deadline(timeout))
                        };
                    }
                    return poll(timeout, || {
                        if read {
                            pthread_rwlock_tryrdlock(lock)
                        } else {
                            pthread_rwlock_trywrlock(lock)
                        }
                    });
                }
                if read {
                    pthread_rwlock_rdlock(lock)
                } else {
                    pthread_rwlock_wrlock(lock)
                }
            }
            #[cfg(target_os = "linux")]
            5 => {
                if operation & LOCK_NB != 0 {
                    return pthread_spin_trylock(storage.cast());
                }
                if timeout > 0 {
                    return poll(timeout, || pthread_spin_trylock(storage.cast()));
                }
                pthread_spin_lock(storage.cast())
            }
            _ => EINVAL,
        }
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_unlock(storage: *mut c_void, kind: i32) -> i32 {
    if !valid(storage, kind) {
        return EINVAL;
    }
    unsafe {
        match kind {
            3 => pthread_mutex_unlock(ptr::addr_of_mut!((*storage.cast::<Mutex>()).lock)),
            1 => pthread_rwlock_unlock(ptr::addr_of_mut!((*storage.cast::<RwLock>()).lock)),
            #[cfg(target_os = "linux")]
            5 => pthread_spin_unlock(storage.cast()),
            _ => EINVAL,
        }
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_destroy(storage: *mut c_void, kind: i32) {
    if !valid(storage, kind) {
        return;
    }
    unsafe {
        match kind {
            3 => {
                let s = storage.cast::<Mutex>();
                pthread_mutexattr_destroy(ptr::addr_of_mut!((*s).attr));
                pthread_mutex_destroy(ptr::addr_of_mut!((*s).lock));
            }
            1 => {
                let s = storage.cast::<RwLock>();
                pthread_rwlockattr_destroy(ptr::addr_of_mut!((*s).attr));
                pthread_rwlock_destroy(ptr::addr_of_mut!((*s).lock));
            }
            #[cfg(target_os = "linux")]
            5 => {
                pthread_spin_destroy(storage.cast());
            }
            _ => (),
        }
    }
}

// Generic operations preserve unsigned/signed wrapping and __sync CAS/add/sub fences.
// op: load=0, store=1, add-fetch=2, sub-fetch=3, compare-set=4 (expected last).
macro_rules! atomic_api {
    ($name:ident, $atomic:ty, $word:ty) => {
        #[unsafe(no_mangle)]
        pub unsafe extern "C" fn $name(
            storage: *mut $word,
            op: u32,
            value: $word,
            expected: $word,
        ) -> $word {
            if storage.is_null() || !(storage as usize).is_multiple_of(align_of::<$atomic>()) {
                return 0;
            }
            let a = unsafe { <$atomic>::from_ptr(storage) };
            match op {
                0 => a.load(Ordering::Relaxed),
                1 => {
                    a.store(value, Ordering::Relaxed);
                    value
                }
                2 => a.fetch_add(value, Ordering::SeqCst).wrapping_add(value),
                3 => a.fetch_sub(value, Ordering::SeqCst).wrapping_sub(value),
                4 => a
                    .compare_exchange(expected, value, Ordering::SeqCst, Ordering::SeqCst)
                    .is_ok() as $word,
                _ => 0,
            }
        }
    };
}
atomic_api!(swr_v1_locks_atomic32, AtomicU32, u32);
atomic_api!(swr_v1_locks_atomic64, AtomicI64, i64);

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_barrier_init(
    count: *mut u32,
    arrived: *mut u32,
    parties: u32,
) {
    unsafe {
        swr_v1_locks_atomic32(count, 1, parties, 0);
        swr_v1_locks_atomic32(arrived, 1, 0, 0);
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_barrier_wait(count: *mut u32, arrived: *mut u32) {
    if count.is_null() || arrived.is_null() {
        return;
    }
    unsafe {
        swr_v1_locks_atomic32(arrived, 2, 1, 0);
        while swr_v1_locks_atomic32(arrived, 0, 0, 0) != swr_v1_locks_atomic32(count, 0, 0, 0) {
            usleep(10_000);
            std::sync::atomic::fence(Ordering::SeqCst);
        }
    }
}

// Native pthread storage is borrowed, never moved or exposed as a Rust reference.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_pthread_barrier(
    storage: *mut c_void,
    storage_len: usize,
    attr: *mut c_void,
    attr_len: usize,
    operation: u32,
    shared: i32,
    parties: u32,
) -> i32 {
    #[cfg(target_os = "linux")]
    unsafe {
        if storage.is_null()
            || storage_len != size_of::<pthread_barrier_t>()
            || !(storage as usize).is_multiple_of(align_of::<pthread_barrier_t>())
            || attr.is_null()
            || attr_len != size_of::<pthread_barrierattr_t>()
            || !(attr as usize).is_multiple_of(align_of::<pthread_barrierattr_t>())
        {
            return EINVAL;
        }
        match operation {
            0 => {
                if shared != 0 {
                    pthread_barrierattr_init(attr.cast());
                    pthread_barrierattr_setpshared(attr.cast(), PTHREAD_PROCESS_SHARED);
                }
                pthread_barrier_init(
                    storage.cast(),
                    if shared != 0 {
                        attr.cast()
                    } else {
                        ptr::null()
                    },
                    parties,
                )
            }
            1 => pthread_barrier_wait(storage.cast()),
            2 => {
                let result = pthread_barrier_destroy(storage.cast());
                if shared != 0 {
                    pthread_barrierattr_destroy(attr.cast());
                }
                result
            }
            _ => EINVAL,
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = (
            storage,
            storage_len,
            attr,
            attr_len,
            operation,
            shared,
            parties,
        );
        ENOTSUP
    }
}

/// Futex wait on a native atomic word: consume a ready token, otherwise one
/// FUTEX_WAIT syscall. Non-futex builds use upstream's C++ wait registry.
/// # Safety
/// Word is aligned, live, process-shared u32 storage accessed only atomically.
#[cfg(target_os = "linux")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_wait(word: *mut u32, timeout: f64) -> i32 {
    if word.is_null() || !(word as usize).is_multiple_of(align_of::<AtomicU32>()) {
        return -1;
    }
    let a = unsafe { AtomicU32::from_ptr(word) };
    if a.compare_exchange(1, 0, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok()
    {
        return 0;
    }
    let duration = timespec {
        tv_sec: timeout as time_t,
        tv_nsec: ((timeout - (timeout as time_t) as f64) * 1000.0 * 1000.0 * 1000.0) as c_long,
    };
    let result = unsafe {
        syscall(
            SYS_futex,
            word,
            FUTEX_WAIT,
            0,
            if timeout > 0.0 {
                &duration as *const timespec
            } else {
                ptr::null()
            },
            ptr::null::<c_void>(),
            0,
        )
    };
    if result == 0
        && a.compare_exchange(1, 0, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok()
    {
        0
    } else {
        -1
    }
}
/// # Safety
/// Same requirements as [`swr_v1_locks_wait`].
#[cfg(target_os = "linux")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_wakeup(word: *mut u32, n: i32) -> i32 {
    if word.is_null() || !(word as usize).is_multiple_of(align_of::<AtomicU32>()) {
        return -1;
    }
    let a = unsafe { AtomicU32::from_ptr(word) };
    if a.compare_exchange(0, 1, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok()
    {
        unsafe {
            syscall(
                SYS_futex,
                word,
                FUTEX_WAKE,
                n,
                ptr::null::<c_void>(),
                ptr::null::<c_void>(),
                0,
            ) as i32
        }
    } else {
        0
    }
}

// 0=reentrant, 1=acquired, 2=busy, 3=wait. Cookie/CID values are copied tokens.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_coroutine_try(
    word: *mut u32,
    held_cookie: usize,
    held_cid: i64,
    current_cookie: usize,
    current_cid: i64,
    blocking: u8,
) -> i32 {
    if word.is_null() || !(word as usize).is_multiple_of(align_of::<AtomicU32>()) {
        return -1;
    }
    if current_cookie == held_cookie && current_cid == held_cid {
        return 0;
    }
    let a = unsafe { AtomicU32::from_ptr(word) };
    if a.compare_exchange(0, 1, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok()
    {
        1
    } else if blocking == 0 {
        2
    } else {
        3
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_locks_coroutine_release(word: *mut u32) -> i32 {
    if word.is_null() || !(word as usize).is_multiple_of(align_of::<AtomicU32>()) {
        return -1;
    }
    let a = unsafe { AtomicU32::from_ptr(word) };
    if a.load(Ordering::Relaxed) == 0 {
        return 0;
    }
    a.store(0, Ordering::Relaxed);
    1
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_locks_coroutine_backoff(second: f64, initial: f64, maximum: f64) -> f64 {
    if second >= maximum {
        initial
    } else if second * 2.0 < maximum {
        second * 2.0
    } else {
        maximum
    }
}
