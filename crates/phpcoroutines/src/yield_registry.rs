//! Sole thread-local user-yield frontend registry; values are opaque native tokens.
use std::cell::RefCell;
use std::collections::HashMap;
use std::hash::{BuildHasherDefault, DefaultHasher};

type Registry = HashMap<i64, usize, BuildHasherDefault<DefaultHasher>>;
thread_local! {
    static YIELDED: RefCell<Registry> = RefCell::new(Registry::default());
}

#[unsafe(no_mangle)]
pub(crate) extern "C" fn swr_v1_phpcoroutines_yield_put(cid: i64, token: usize) {
    YIELDED.with_borrow_mut(|registry| {
        registry.insert(cid, token);
    });
}

/// Remove before returning to native resume/yield effects, never across them.
/// # Safety
/// `token` is writable for one usize. Its referent is never accessed by Rust.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_take(cid: i64, token: *mut usize) -> u8 {
    YIELDED.with_borrow_mut(|registry| match registry.remove(&cid) {
        Some(value) => {
            // SAFETY: `token` is writable for one usize and doesn't alias the registry.
            unsafe { *token = value };
            1
        }
        None => 0,
    })
}

#[unsafe(no_mangle)]
pub(crate) extern "C" fn swr_v1_phpcoroutines_yield_erase(cid: i64) {
    YIELDED.with_borrow_mut(|registry| {
        registry.remove(&cid);
    });
}

/// Native `SW_THREAD_LOCAL` custody owns this opaque allocation. It is global when
/// `SW_THREAD` is off, per-thread when on; no separate Rust global registry exists.
pub(crate) struct YieldRegistry(Registry);

/// # Safety
/// `owner` is writable exclusive native owner storage, initially null. Keep its
/// handle until native destruction and serialize operations like the original map.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_registry_put(
    owner: *mut *mut YieldRegistry,
    cid: i64,
    token: usize,
) {
    // SAFETY: per this function's `# Safety` contract, `owner` is live, aligned and exclusive.
    let owner = unsafe { &mut *owner };
    if owner.is_null() {
        *owner = Box::into_raw(Box::new(YieldRegistry(Registry::default())));
    }
    // SAFETY: the slot now holds a live, exclusive handle (created above if it was null).
    unsafe { &mut **owner }.0.insert(cid, token);
}

/// # Safety
/// A nonnull handle is live/exclusive. Output is writable and does not alias its
/// storage. A null handle denotes the original empty, unallocated native map.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_registry_take(
    registry: *mut YieldRegistry,
    cid: i64,
    token: *mut usize,
) -> u8 {
    // SAFETY: `registry` is null or live, aligned and exclusively lent for this call.
    let Some(registry) = (unsafe { registry.as_mut() }) else {
        return 0;
    };
    match registry.0.remove(&cid) {
        Some(value) => {
            // SAFETY: `token` is writable for one usize and doesn't alias the registry.
            unsafe { *token = value };
            1
        }
        None => 0,
    }
}

/// # Safety
/// A nonnull handle is live/exclusive. Null denotes an empty unallocated map.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_registry_erase(
    registry: *mut YieldRegistry,
    cid: i64,
) {
    // SAFETY: `registry` is null or live, aligned and exclusively lent for this call.
    if let Some(registry) = unsafe { registry.as_mut() } {
        registry.0.remove(&cid);
    }
}

/// # Safety
/// Consume the handle exactly once at its native owner's destruction. Only opaque
/// metadata drops, never referents. Null is accepted for an empty native owner.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_registry_drop(
    registry: *mut YieldRegistry,
) {
    if !registry.is_null() {
        // SAFETY: a non-null owned handle, consumed exactly once at native destruction.
        unsafe { drop(Box::from_raw(registry)) };
    }
}

/// Fallible admission preserving lazy native owner publication and existing keys.
/// # Safety
/// Owner storage is live/writable/exclusive, initially null or one live handle.
/// Failure publishes neither a new owner nor token; referents remain native.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_yield_registry_try_put(
    owner: *mut *mut YieldRegistry,
    cid: i64,
    token: usize,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `owner` is live, aligned and exclusive.
    let owner = unsafe { &mut *owner };
    if owner.is_null() {
        let ptr = crate::allocation::try_owned(YieldRegistry(Registry::default()));
        if ptr.is_null() {
            return 0;
        }
        // SAFETY: a fresh, non-null allocation from `try_owned`, uniquely owned here.
        let mut candidate = unsafe { Box::from_raw(ptr) };
        if candidate.0.try_reserve(1).is_err() {
            return 0;
        }
        candidate.0.insert(cid, token);
        *owner = Box::into_raw(candidate);
        return 1;
    }
    // SAFETY: a non-null slot holds one live, exclusive handle.
    let registry = &mut unsafe { &mut **owner }.0;
    if let Some(existing) = registry.get_mut(&cid) {
        *existing = token;
        return 1;
    }
    if registry.try_reserve(1).is_err() {
        return 0;
    }
    registry.insert(cid, token);
    1
}
