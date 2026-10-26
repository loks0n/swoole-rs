//! Sole LIFO of opaque callback tokens, with explicit fallible admission.
pub struct DeferredCallbacks(Vec<usize>);

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_defer_new() -> *mut DeferredCallbacks {
    crate::allocation::try_owned(DeferredCallbacks(Vec::new()))
}
/// # Safety
/// The handle is live/exclusive. Zero reports failed capacity/allocation admission
/// without publishing a token; the native caller throws only after Rust returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_defer_push(
    queue: *mut DeferredCallbacks,
    token: usize,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `queue` is live, aligned and exclusive.
    let tokens = &mut unsafe { &mut *queue }.0;
    if tokens.try_reserve(1).is_err() {
        return 0;
    }
    tokens.push(token);
    1
}
/// # Safety
/// The handle is live/exclusive, output writable/non-aliasing. Removes before
/// native effects; empty leaves output untouched. Token referents are never read.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_defer_pop(
    queue: *mut DeferredCallbacks,
    token: *mut usize,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `queue` is live, aligned and exclusive.
    match unsafe { &mut *queue }.0.pop() {
        Some(value) => {
            // SAFETY: `token` is writable and does not alias the queue (see the contract).
            unsafe { *token = value };
            1
        }
        None => 0,
    }
}
/// # Safety
/// Consume the live handle once, after native payload cleanup. Only metadata drops.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_defer_drop(queue: *mut DeferredCallbacks) {
    // SAFETY: the owned handle from `try_owned`, consumed exactly once.
    unsafe { drop(Box::from_raw(queue)) };
}
