//! Sole scheduler metadata in the existing Native TLS scope. Native registry,
//! context/thread setup and callbacks run only after these calls return.
use core::ffi::c_long;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CoroutineScheduler {
    pub stack_size: usize,
    pub last_cid: c_long,
    pub socket_bound_cid: c_long,
    pub peak_num: u64,
    pub activated: u8,
}

const STACK_MIN: usize = 64 * 1024;
const STACK_MAX: usize = 16 * 1024 * 1024;
const STACK_ALIGNMENT: usize = 4 * 1024;

/// # Safety
/// `state` is a live aligned record in the calling thread's Native scope.
/// No concurrent mutation may race this call. Original signed arithmetic must
/// be defined; wrapping beyond that domain is not a Native compatibility claim.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_next_id(
    state: *mut CoroutineScheduler,
) -> c_long {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    next_id(unsafe { &mut *state })
}

pub(crate) fn next_id(state: &mut CoroutineScheduler) -> c_long {
    state.last_cid = state.last_cid.wrapping_add(1);
    state.last_cid
}

/// Registration stage0 requests fresh count/peak publication; stage1 separately
/// decides activation at its original later observation. No registry pointer is retained.
/// # Safety
/// `state` is a live aligned readable record without concurrent mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_registration(
    state: *const CoroutineScheduler,
    count: usize,
    stage: u32,
) -> u32 {
    // SAFETY: `state` is a live, aligned, readable record without concurrent mutation.
    let state = unsafe { &*state };
    match stage {
        0 => u32::from(count as u64 > state.peak_num),
        1 => u32::from(state.activated == 0),
        _ => 0,
    }
}

/// # Safety
/// `state` is a live aligned record without racing reads/writes. `count` is the
/// original second observation after a requested peak publication, even if it
/// differs from the first observation. Do not replace publication with `max()`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_publish_peak(
    state: *mut CoroutineScheduler,
    count: usize,
) {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    state.peak_num = count as u64;
}

/// # Safety
/// `state` is a live aligned record without racing reads/writes. Native class
/// constants are statically checked against these pinned limit/alignment values.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_set_stack_size(
    state: *mut CoroutineScheduler,
    requested: usize,
) {
    let bounded = requested.clamp(STACK_MIN, STACK_MAX);
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    state.stack_size = (bounded + STACK_ALIGNMENT - 1) & !(STACK_ALIGNMENT - 1);
}

/// # Safety
/// `state` is a live aligned record without racing reads/writes. Native effects
/// before/after activation publication remain entirely in the Native caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_set_active(
    state: *mut CoroutineScheduler,
    active: u8,
) {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    state.activated = u8::from(active != 0);
}

/// # Safety
/// `state` is a live aligned record without racing reads/writes. Signed socket
/// binding IDs, including negative sentinels, are preserved without conversion.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_scheduler_bind_socket(
    state: *mut CoroutineScheduler,
    cid: c_long,
) {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    state.socket_bound_cid = cid;
}

#[cfg(test)]
mod tests {
    use super::*;
    fn seed() -> CoroutineScheduler {
        CoroutineScheduler {
            stack_size: 2 * 1024 * 1024,
            last_cid: 0,
            socket_bound_cid: 0,
            peak_num: 0,
            activated: 0,
        }
    }
    #[test]
    fn registration_retains_second_observation_and_activation_publication() {
        let mut s = seed();
        unsafe {
            assert_eq!(swr_v1_coroutine_scheduler_next_id(&raw mut s), 1);
            assert_eq!(
                swr_v1_coroutine_scheduler_registration(&raw const s, 7, 0),
                1
            );
            swr_v1_coroutine_scheduler_publish_peak(&raw mut s, 5);
            assert_eq!(
                swr_v1_coroutine_scheduler_registration(&raw const s, 0, 1),
                1
            );
            swr_v1_coroutine_scheduler_set_active(&raw mut s, 1);
            assert_eq!(
                swr_v1_coroutine_scheduler_registration(&raw const s, 0, 1),
                0
            );
            assert_eq!(
                swr_v1_coroutine_scheduler_registration(&raw const s, 5, 0),
                0
            );
            assert_eq!(
                swr_v1_coroutine_scheduler_registration(&raw const s, 6, 0),
                1
            );
            swr_v1_coroutine_scheduler_bind_socket(&raw mut s, -1);
        }
        assert_eq!(s.peak_num, 5);
        assert_eq!(s.socket_bound_cid, -1);
    }
    #[test]
    fn stack_limits_alignment_and_signed_ids_preserve_defined_domain() {
        let mut s = seed();
        for (requested, expected) in [
            (0, STACK_MIN),
            (1, STACK_MIN),
            (STACK_MIN - 1, STACK_MIN),
            (STACK_MIN, STACK_MIN),
            (STACK_MIN + 1, STACK_MIN + STACK_ALIGNMENT),
            (STACK_MAX - 1, STACK_MAX),
            (STACK_MAX, STACK_MAX),
            (usize::MAX, STACK_MAX),
        ] {
            unsafe {
                swr_v1_coroutine_scheduler_set_stack_size(&raw mut s, requested);
            }
            assert_eq!(s.stack_size, expected);
        }
        s.last_cid = -3;
        unsafe {
            assert_eq!(swr_v1_coroutine_scheduler_next_id(&raw mut s), -2);
        }
    }
}
