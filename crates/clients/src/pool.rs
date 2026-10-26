//! Sole private persistent-Client container. Tokens are never dereferenced/dropped.
use std::alloc::{Layout, alloc, dealloc};
use std::collections::{HashMap, VecDeque};
use std::ffi::c_void;
use std::hash::{BuildHasherDefault, DefaultHasher};

#[cfg(test)]
std::thread_local! {
    // Logical fallible allocation sites only; not a claim about malloc topology.
    static ALLOCATION_BUDGET: std::cell::Cell<Option<usize>> = const { std::cell::Cell::new(None) };
}

#[inline]
fn allocation_allowed() -> bool {
    #[cfg(test)]
    {
        ALLOCATION_BUDGET.with(|budget| match budget.get() {
            None => true,
            Some(0) => false,
            Some(left) => {
                budget.set(Some(left - 1));
                true
            }
        })
    }
    #[cfg(not(test))]
    {
        true
    }
}

#[cfg(test)]
#[unsafe(no_mangle)]
pub extern "C" fn swr_test_clients_pool_allocation_budget(budget: isize) {
    ALLOCATION_BUDGET.with(|value| value.set(usize::try_from(budget).ok()));
}

type Queues = HashMap<Vec<u8>, VecDeque<*mut c_void>, BuildHasherDefault<DefaultHasher>>;
struct Pool {
    queues: Queues,
}
const OK: u32 = 0;
const OUT_OF_MEMORY: u32 = 1;
const INVALID_ARGUMENT: u32 = 2;

unsafe fn key<'a>(data: *const u8, length: usize) -> Option<&'a [u8]> {
    if length == 0 {
        Some(&[])
    } else if data.is_null() || length > isize::MAX as usize {
        None
    } else {
        // SAFETY: `data` is non-null and `length <= isize::MAX` (checked above); the caller lends `length` initialized bytes for this call.
        Some(unsafe { std::slice::from_raw_parts(data, length) })
    }
}

/// Creates only the opaque owner; bucket/key/queue allocations remain lazy and
/// fallible. No native effects, entropy, user callbacks or Client destruction.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_pool_create() -> *mut c_void {
    if !allocation_allowed() {
        return std::ptr::null_mut();
    }
    #[expect(
        clippy::cast_ptr_alignment,
        reason = "alloc honours Layout::new::<Pool>()"
    )]
    // SAFETY: `Pool` is not zero-sized; null is handled below.
    let memory = unsafe { alloc(Layout::new::<Pool>()) }.cast::<Pool>();
    if !memory.is_null() {
        // SAFETY: `memory` is a fresh, non-null allocation with `Pool`'s layout.
        unsafe {
            memory.write(Pool {
                queues: HashMap::with_hasher(BuildHasherDefault::default()),
            });
        }
    }
    memory.cast()
}

/// # Safety
/// Handle is null or a live unique owner returned by create, with no active calls.
/// Drops Rust container buffers only. Opaque Client tokens never run destructors.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_pool_destroy(handle: *mut c_void) {
    if !handle.is_null() {
        let pool = handle.cast::<Pool>();
        // SAFETY: a live, uniquely owned pool from `swr_v1_clients_pool_create`.
        unsafe { std::ptr::drop_in_place(pool) };
        // SAFETY: allocated with this layout by create; its value was just dropped.
        unsafe { dealloc(pool.cast(), Layout::new::<Pool>()) };
    }
}

/// # Safety
/// Handle is live with exclusive access. Key bytes are initialized and independent
/// of pool storage. Token is nonnull and remains under native Client custody.
/// 0 success;1 fallible allocation failed;2 invalid argument. New empty entry is
/// published before queue growth, preserving its logical failure prefix.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_pool_push(
    handle: *mut c_void,
    data: *const u8,
    length: usize,
    token: *mut c_void,
) -> u32 {
    // SAFETY: key bytes are initialized for `length` (null only when empty) for this call.
    let Some(key) = (unsafe { key(data, length) }) else {
        return INVALID_ARGUMENT;
    };
    if handle.is_null() || token.is_null() {
        return INVALID_ARGUMENT;
    }
    // SAFETY: non-null (checked above); a live pool from `swr_v1_clients_pool_create`, exclusively accessed.
    let pool = unsafe { &mut *handle.cast::<Pool>() };
    if !pool.queues.contains_key(key) {
        let mut owned = Vec::new();
        if !key.is_empty() && (!allocation_allowed() || owned.try_reserve_exact(key.len()).is_err())
        {
            return OUT_OF_MEMORY;
        }
        owned.extend_from_slice(key);
        if pool.queues.len() == pool.queues.capacity()
            && (!allocation_allowed() || pool.queues.try_reserve(1).is_err())
        {
            return OUT_OF_MEMORY;
        }
        pool.queues.insert(owned, VecDeque::new());
    }
    let Some(queue) = pool.queues.get_mut(key) else {
        return INVALID_ARGUMENT;
    };
    if queue.len() == queue.capacity() && (!allocation_allowed() || queue.try_reserve(1).is_err()) {
        return OUT_OF_MEMORY;
    }
    queue.push_back(token);
    OK
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct PoolState {
    pub kind: u32,
    pub length: usize,
}

/// # Safety
/// Handle is null or live, key initialized and independent, no concurrent writes.
/// Returns0 absent,1 present-empty,2 present-nonempty; allocates nothing.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_pool_state(
    handle: *const c_void,
    data: *const u8,
    length: usize,
) -> PoolState {
    // SAFETY: key bytes are initialized for `length` (null only when empty) for this call.
    let Some(key) = (unsafe { key(data, length) }) else {
        return PoolState::default();
    };
    if handle.is_null() {
        return PoolState::default();
    }
    // SAFETY: non-null (checked above); a live pool from `swr_v1_clients_pool_create`.
    match unsafe { &*handle.cast::<Pool>() }.queues.get(key) {
        None => PoolState::default(),
        Some(queue) => PoolState {
            kind: if queue.is_empty() { 1 } else { 2 },
            length: queue.len(),
        },
    }
}

/// # Safety
/// Handle is null or live with exclusive access; key is initialized/independent.
/// Returns the FIFO native token or null, retaining the now-empty entry.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_pool_take(
    handle: *mut c_void,
    data: *const u8,
    length: usize,
) -> *mut c_void {
    // SAFETY: key bytes are initialized for `length` (null only when empty) for this call.
    let Some(key) = (unsafe { key(data, length) }) else {
        return std::ptr::null_mut();
    };
    if handle.is_null() {
        return std::ptr::null_mut();
    }
    // SAFETY: non-null (checked above); a live pool from `swr_v1_clients_pool_create`, exclusively accessed.
    unsafe { &mut *handle.cast::<Pool>() }
        .queues
        .get_mut(key)
        .and_then(VecDeque::pop_front)
        .unwrap_or(std::ptr::null_mut())
}

/// # Safety
/// Handle is null or live with exclusive access; key is initialized/independent.
/// Removes only present-empty entries; never closes/destroys native tokens.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_pool_remove_empty(
    handle: *mut c_void,
    data: *const u8,
    length: usize,
) -> u8 {
    // SAFETY: key bytes are initialized for `length` (null only when empty) for this call.
    let Some(key) = (unsafe { key(data, length) }) else {
        return 0;
    };
    if handle.is_null() {
        return 0;
    }
    // SAFETY: non-null (checked above); a live pool from `swr_v1_clients_pool_create`, exclusively accessed.
    let pool = unsafe { &mut *handle.cast::<Pool>() };
    if pool.queues.get(key).is_some_and(VecDeque::is_empty) {
        pool.queues.remove(key);
        1
    } else {
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct BudgetReset;
    impl Drop for BudgetReset {
        fn drop(&mut self) {
            swr_test_clients_pool_allocation_budget(-1);
        }
    }
    #[test]
    fn fifo_binary_keys_empty_prefix_and_allocation_failures() {
        let _reset = BudgetReset;
        swr_test_clients_pool_allocation_budget(0);
        assert!(swr_v1_clients_pool_create().is_null());
        swr_test_clients_pool_allocation_budget(-1);
        let handle = swr_v1_clients_pool_create();
        assert!(!handle.is_null());
        let key = b"pool\0binary";
        let first = std::ptr::without_provenance_mut::<c_void>(1);
        let second = std::ptr::without_provenance_mut::<c_void>(2);
        for budget in 0..=2 {
            swr_test_clients_pool_allocation_budget(budget);
            assert_eq!(
                unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), first) },
                OUT_OF_MEMORY
            );
            let expected = if budget == 2 { 1 } else { 0 };
            assert_eq!(
                unsafe { swr_v1_clients_pool_state(handle, key.as_ptr(), key.len()) }.kind,
                expected
            );
        }
        swr_test_clients_pool_allocation_budget(-1);
        assert_eq!(
            unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), first) },
            OK
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), second) },
            OK
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_state(handle, key.as_ptr(), key.len()) }.length,
            2
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_remove_empty(handle, key.as_ptr(), key.len()) },
            0
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_take(handle, key.as_ptr(), key.len()) },
            first
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_take(handle, key.as_ptr(), key.len()) },
            second
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_state(handle, key.as_ptr(), key.len()) }.kind,
            1
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_remove_empty(handle, key.as_ptr(), key.len()) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_state(handle, key.as_ptr(), key.len()) }.kind,
            0
        );
        unsafe {
            swr_v1_clients_pool_destroy(handle);
        }
    }
    #[test]
    fn queue_growth_failure_keeps_existing_fifo_and_tokens() {
        let _reset = BudgetReset;
        let handle = swr_v1_clients_pool_create();
        assert!(!handle.is_null());
        let key = b"growth";
        let token = std::ptr::without_provenance_mut::<c_void>(7);
        assert_eq!(
            unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), token) },
            OK
        );
        // SAFETY: non-null (checked above); a live pool from `swr_v1_clients_pool_create`.
        let capacity = unsafe { &*handle.cast::<Pool>() }
            .queues
            .get(key.as_slice())
            .map(VecDeque::capacity)
            .unwrap();
        for _ in 1..capacity {
            assert_eq!(
                unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), token) },
                OK
            );
        }
        swr_test_clients_pool_allocation_budget(0);
        assert_eq!(
            unsafe { swr_v1_clients_pool_push(handle, key.as_ptr(), key.len(), token) },
            OUT_OF_MEMORY
        );
        assert_eq!(
            unsafe { swr_v1_clients_pool_state(handle, key.as_ptr(), key.len()) }.length,
            capacity
        );
        for _ in 0..capacity {
            assert_eq!(
                unsafe { swr_v1_clients_pool_take(handle, key.as_ptr(), key.len()) },
                token
            );
        }
        assert!(unsafe { swr_v1_clients_pool_take(handle, key.as_ptr(), key.len()) }.is_null());
        unsafe {
            swr_v1_clients_pool_destroy(handle);
        }
    }
}
