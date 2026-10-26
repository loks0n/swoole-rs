//! Complete creation/CID registration protocol. Native Context already
//! exists before entry; Native map/activation/exception/delete effects follow return.
use crate::CoroutineScheduler;
use core::ffi::c_long;

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

/// Whole constructor-body registration through the Native map effect protocol.
/// Peak publication keeps two fresh observations.
/// ACTIVATE and DONE are terminal: Native must return immediately after its
/// requested activation effect, without a further object/cursor observation.
/// # Safety
/// Cursor is exclusive initialized caller-local storage. Before phase0, Native
/// Context construction has completed. CID is raw writable possibly uninitialized
/// cell storage, initialized here before any read. Scheduler is live initialized
/// exclusive storage, distinct from cursor/CID. Signed counter arithmetic must be
/// defined as in Native. Native alone handles allocation exceptions and
/// activation, with no added rollback on failure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_create_step(
    cursor: *mut CoroutineCreationCursor,
    scheduler: *mut CoroutineScheduler,
    cid: *mut CoroutineCid,
    observed_count: usize,
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
            cursor.phase = 1;
            CoroutineCreationAction {
                action: INSERT,
                cid: value,
            }
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

#[cfg(test)]
mod tests {
    use super::*;
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
            let step =
                swr_v1_coroutine_create_step(&mut cursor, &mut scheduler, cid.as_mut_ptr(), 0);
            assert_eq!((step.action, step.cid), (INSERT, 1));
            assert_eq!(swr_v1_coroutine_cid_read(cid.as_ptr()), 1);
            assert_eq!(scheduler.peak_num, 0);
            assert_eq!(
                swr_v1_coroutine_create_step(&mut cursor, &mut scheduler, cid.as_mut_ptr(), 0)
                    .action,
                COUNT
            );
            assert_eq!(
                swr_v1_coroutine_create_step(&mut cursor, &mut scheduler, cid.as_mut_ptr(), 7)
                    .action,
                COUNT
            );
            assert_eq!(
                swr_v1_coroutine_create_step(&mut cursor, &mut scheduler, cid.as_mut_ptr(), 5)
                    .action,
                ACTIVATE
            );
            assert_eq!(scheduler.peak_num, 5);
            // Terminal only reads the caller-local cursor, not object/state.
            assert_eq!(
                swr_v1_coroutine_create_step(&mut cursor, ptr::null_mut(), ptr::null_mut(), 0)
                    .action,
                DONE
            );
        }
    }
}
