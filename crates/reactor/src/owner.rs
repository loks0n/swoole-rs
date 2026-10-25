//! Private fallible ownership for Rust-only metadata. Native tokens are inert.
use std::alloc::{Layout, alloc};
use std::mem::MaybeUninit;

// Allocate before initialization, retaining each caller's storage/owner order.
pub(crate) fn try_owner<T>(initialize: impl FnOnce() -> T) -> Option<Box<T>> {
    if size_of::<T>() == 0 {
        return Some(Box::new(initialize()));
    }
    let pointer = unsafe { alloc(Layout::new::<T>()).cast::<MaybeUninit<T>>() };
    if pointer.is_null() {
        return None;
    }
    let mut owner = unsafe { Box::from_raw(pointer) };
    owner.write(initialize());
    Some(unsafe { owner.assume_init() })
}

/// # Safety
/// Null or live exclusively-owned global-allocation metadata, detached from all
/// Native consumers. T owns only Rust metadata; no Native payload is dropped.
pub(crate) unsafe fn release<T>(owner: *mut T) {
    if !owner.is_null() {
        drop(unsafe { Box::from_raw(owner) });
    }
}

/// # Safety
/// Exclusive live opaque slot, null or pointing to T from the same allocator.
/// No reference/token may escape operation or cross a Native effect. Admission
/// precedes this call; true publishes only after the safe operation succeeds.
pub(crate) unsafe fn publish<T>(
    slot: &mut *mut T,
    initialize: impl FnOnce() -> T,
    operation: impl FnOnce(&mut T) -> Result<(i32, bool), i32>,
) -> Result<i32, i32> {
    if let Some(owner) = unsafe { (*slot).as_mut() } {
        return operation(owner).map(|(result, _)| result);
    }
    let mut owner = try_owner(initialize).ok_or(-2)?;
    let (result, committed) = operation(&mut owner)?;
    if committed {
        *slot = Box::into_raw(owner);
    }
    Ok(result)
}
