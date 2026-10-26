//! Complete creation/CID/registry registration protocol. Native Context already
//! exists before entry; Native map/activation/exception/delete effects follow return.
use crate::CoroutineScheduler;
use core::ffi::{c_long, c_void};

#[repr(C)]
pub struct CoroutineCid {
    pub value: c_long,
}

#[repr(C)]
pub struct CoroutineCreationCursor {
    pub phase: u32,
}

#[repr(C)]
pub struct CoroutineCreationAction {
    pub action: i32,
    pub cid: c_long,
}

const DONE: i32 = 0;
const INSERT: i32 = 1;
const COUNT: i32 = 2;
const ACTIVATE: i32 = 3;
const FINISHED: u32 = 4;

fn terminal(
    cursor: &mut CoroutineCreationCursor,
    scheduler: &CoroutineScheduler,
) -> CoroutineCreationAction {
    cursor.phase = FINISHED;
    CoroutineCreationAction {
        action: if scheduler.activated == 0 {
            ACTIVATE
        } else {
            DONE
        },
        cid: 0,
    }
}

/// # Safety
/// Initialized readable CID cell in a live Native object, without racing access.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_cid_read(cid: *const CoroutineCid) -> c_long {
    // SAFETY: per this function's `# Safety` contract, `cid` is live, aligned and initialized.
    unsafe { (*cid).value }
}

/// Whole constructor-body registration. Null registry slot selects the genuine
/// Native map effect protocol; non-null selects the existing qualified Rust
/// owner, not a second registry. Peak publication keeps two fresh observations.
/// ACTIVATE and DONE are terminal: Native must return immediately after its
/// requested activation effect, without a further object/cursor observation.
/// # Safety
/// Cursor is exclusive initialized caller-local storage. Before phase0, Native
/// Context construction has completed. CID is raw writable possibly uninitialized
/// cell storage, initialized here before any read. Scheduler is live initialized
/// exclusive storage, distinct from cursor/CID/owner slot. A non-null owner slot
/// contains null or the existing live serialized Registry; tokens are opaque.
/// Signed counter arithmetic must be defined as in Native. Native alone handles
/// allocation exceptions and activation, with no added rollback on failure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_create_step(
    cursor: *mut CoroutineCreationCursor,
    scheduler: *mut CoroutineScheduler,
    cid: *mut CoroutineCid,
    registry: *mut *mut c_void,
    token: usize,
    observed_count: usize,
) -> CoroutineCreationAction {
    // SAFETY: forwards the caller's cursor, scheduler, CID and owner-slot contract.
    unsafe {
        create_step(
            cursor,
            scheduler,
            cid,
            registry,
            token,
            observed_count,
            None,
        )
    }
}

/// Whole qualified-owner creation with an explicit Native compiler capsule.
/// # Safety
/// Same initialized/raw-storage/effect contract as create_step. Policy selection
/// happens only on actual registration, after original raw CID publication.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_selected_create_step(
    cursor: *mut CoroutineCreationCursor,
    scheduler: *mut CoroutineScheduler,
    cid: *mut CoroutineCid,
    registry: *mut *mut c_void,
    token: usize,
    observed_count: usize,
    policy: crate::registry::CoroutineRegistryPolicy,
) -> CoroutineCreationAction {
    // SAFETY: forwards the caller's cursor, scheduler, CID and owner-slot contract.
    unsafe {
        create_step(
            cursor,
            scheduler,
            cid,
            registry,
            token,
            observed_count,
            Some(policy),
        )
    }
}

unsafe fn create_step(
    cursor: *mut CoroutineCreationCursor,
    scheduler: *mut CoroutineScheduler,
    cid: *mut CoroutineCid,
    registry: *mut *mut c_void,
    token: usize,
    observed_count: usize,
    policy: Option<crate::registry::CoroutineRegistryPolicy>,
) -> CoroutineCreationAction {
    // SAFETY: per this function's `# Safety` contract, `cursor` is live, aligned and exclusive.
    let cursor = unsafe { &mut *cursor };
    if cursor.phase == FINISHED {
        return CoroutineCreationAction {
            action: DONE,
            cid: 0,
        };
    }
    if cursor.phase > FINISHED {
        return CoroutineCreationAction { action: -4, cid: 0 };
    }
    // SAFETY: per this function's `# Safety` contract, `scheduler` is live, aligned and exclusive.
    let scheduler = unsafe { &mut *scheduler };
    match cursor.phase {
        0 => {
            let value = crate::scheduler::next_id(scheduler);
            // SAFETY: per this function's `# Safety` contract, `cid` is live, aligned and writable.
            unsafe { cid.write(CoroutineCid { value }) };
            if registry.is_null() {
                cursor.phase = 1;
                return CoroutineCreationAction {
                    action: INSERT,
                    cid: value,
                };
            }
            // A non-null slot holds null or the live, serialized Registry.
            let result = match policy {
                // SAFETY: as above.
                Some(policy) => unsafe {
                    crate::registry::selected_insert(registry, value, token, policy)
                },
                // SAFETY: as above.
                None => unsafe { crate::registry::insert(registry, value, token) },
            };
            if result != 0 {
                cursor.phase = FINISHED;
                return CoroutineCreationAction {
                    action: result,
                    cid: 0,
                };
            }
            // The insert succeeded, so the slot now holds the live, serialized Registry.
            // SAFETY: as above.
            let owner = unsafe { *registry };
            // SAFETY: as above.
            let first_count = unsafe { crate::registry::count(owner) };
            if first_count as u64 > scheduler.peak_num {
                // SAFETY: as above.
                let owner = unsafe { *registry };
                // SAFETY: as above.
                scheduler.peak_num = unsafe { crate::registry::count(owner) } as u64;
            }
            terminal(cursor, scheduler)
        }
        1 => {
            // Native operator[] completed; request the original first count.
            cursor.phase = 2;
            CoroutineCreationAction {
                action: COUNT,
                cid: 0,
            }
        }
        2 if observed_count as u64 > scheduler.peak_num => {
            cursor.phase = 3;
            CoroutineCreationAction {
                action: COUNT,
                cid: 0,
            }
        }
        3 => {
            // Preserve the original second observation, not max(first, second).
            scheduler.peak_num = observed_count as u64;
            terminal(cursor, scheduler)
        }
        _ => terminal(cursor, scheduler),
    }
}

/// Whole close-time CID read/removal from the existing owner. Native delete
/// follows return; there is no access to the Native object/token afterward.
/// # Safety
/// Owner is null or a live exclusive serialized Registry. CID is initialized
/// readable distinct cell storage in the still-live Native object.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_unregister(
    registry: *mut c_void,
    cid: *const CoroutineCid,
) -> usize {
    // SAFETY: `cid` is an initialized, readable cell in the still-live native object.
    let value = unsafe { (*cid).value };
    // SAFETY: `registry` is null or a live, exclusive, serialized Registry.
    unsafe { crate::registry::erase(registry, value) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{swr_v1_coroutine_registry_drop, swr_v1_coroutine_registry_lookup};
    use std::{mem::MaybeUninit, ptr};

    fn scheduler() -> CoroutineScheduler {
        CoroutineScheduler {
            stack_size: 65536,
            last_cid: 0,
            socket_bound_cid: 0,
            peak_num: 0,
            activated: 0,
        }
    }

    #[test]
    fn native_effect_protocol_publishes_raw_cid_and_exact_second_count_then_stops() {
        let mut scheduler = scheduler();
        let mut cursor = CoroutineCreationCursor { phase: 0 };
        let mut cid = MaybeUninit::<CoroutineCid>::uninit();
        unsafe {
            let step = swr_v1_coroutine_create_step(
                &mut cursor,
                &mut scheduler,
                cid.as_mut_ptr(),
                ptr::null_mut(),
                9,
                0,
            );
            assert_eq!((step.action, step.cid), (INSERT, 1));
            assert_eq!(swr_v1_coroutine_cid_read(cid.as_ptr()), 1);
            assert_eq!(scheduler.peak_num, 0);
            assert_eq!(
                swr_v1_coroutine_create_step(
                    &mut cursor,
                    &mut scheduler,
                    cid.as_mut_ptr(),
                    ptr::null_mut(),
                    9,
                    0
                )
                .action,
                COUNT
            );
            assert_eq!(
                swr_v1_coroutine_create_step(
                    &mut cursor,
                    &mut scheduler,
                    cid.as_mut_ptr(),
                    ptr::null_mut(),
                    9,
                    7
                )
                .action,
                COUNT
            );
            assert_eq!(
                swr_v1_coroutine_create_step(
                    &mut cursor,
                    &mut scheduler,
                    cid.as_mut_ptr(),
                    ptr::null_mut(),
                    9,
                    5
                )
                .action,
                ACTIVATE
            );
            assert_eq!(scheduler.peak_num, 5);
            // Terminal only reads the caller-local cursor, not object/state.
            assert_eq!(
                swr_v1_coroutine_create_step(
                    &mut cursor,
                    ptr::null_mut(),
                    ptr::null_mut(),
                    ptr::null_mut(),
                    0,
                    0
                )
                .action,
                DONE
            );
        }
    }

    #[test]
    fn existing_registry_creation_lookup_overwrite_and_predelete_remove_keep_one_owner() {
        let mut scheduler = scheduler();
        let mut owner = ptr::null_mut();
        let mut byte = 1_u8;
        let token = ptr::from_mut(&mut byte) as usize;
        let mut cid = MaybeUninit::<CoroutineCid>::uninit();
        unsafe {
            for active in [0, 1] {
                scheduler.activated = active;
                // Explicit duplicate key exercises HIT without null reset.
                scheduler.last_cid = -1;
                let mut cursor = CoroutineCreationCursor { phase: 0 };
                let action = swr_v1_coroutine_create_step(
                    &mut cursor,
                    &mut scheduler,
                    cid.as_mut_ptr(),
                    &mut owner,
                    token,
                    0,
                );
                assert_eq!(action.action, if active == 0 { ACTIVATE } else { DONE });
                assert_eq!(swr_v1_coroutine_cid_read(cid.as_ptr()), 0);
                assert_eq!(swr_v1_coroutine_registry_lookup(owner, 0), token);
                assert_eq!(crate::registry::count(owner), 1);
                assert_eq!(scheduler.peak_num, 1);
            }
            assert_eq!(swr_v1_coroutine_unregister(owner, cid.as_ptr()), 1);
            assert_eq!(swr_v1_coroutine_unregister(owner, cid.as_ptr()), 0);
            assert_eq!(swr_v1_coroutine_registry_lookup(owner, 0), 0);
            swr_v1_coroutine_registry_drop(&mut owner);
            assert!(owner.is_null());
        }
        assert_eq!(byte, 1);
    }
}
