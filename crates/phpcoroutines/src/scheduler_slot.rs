//! Sole nullable Scheduler list-cell custody. Native payload effects stay outside.
use crate::{SchedulerQueue, SchedulerTask};

/// # Safety
/// Slot is a live/exclusive Native frontend pointer cell, constant-zero seeded
/// or containing its sole Rust SchedulerQueue handle. No Native object enters
/// Rust; only this field address. Runtime accesses are serialized by the existing
/// Native Scheduler owner. Failure leaves the cell unchanged; Native throws only
/// after return. No borrow/frame spans cache persistence, callbacks or Zend.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_prepare_slot(
    slot: *mut *mut SchedulerQueue,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `slot` is live, aligned and initialized.
    if !unsafe { slot.read() }.is_null() {
        return 1;
    }
    let queue = SchedulerQueue::try_new();
    if queue.is_null() {
        0
    } else {
        // SAFETY: per this function's `# Safety` contract, `slot` is live, aligned and writable.
        unsafe { slot.write(queue) };
        1
    }
}
/// # Safety
/// Slot has a live queue following successful preparation, under the same
/// exclusive cell contract. Observe it freshly after Native cache/parameter
/// persistence, as the original caller did. Allocation failure publishes no task.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_try_push_slot(
    slot: *mut *mut SchedulerQueue,
    token: usize,
    count: i64,
) -> u8 {
    // SAFETY: `slot` is the caller's live, exclusive cell.
    let queue = unsafe { slot.read() };
    // SAFETY: the slot holds this module's live, exclusive queue.
    unsafe { &mut *queue }.try_push(token, count)
}
/// Distinguish absent(0), present-empty(1), and removed task(2), preserving the
/// sticky-started missing-queue error versus the valid empty-queue path.
/// # Safety
/// Slot follows the live/exclusive contract; output is writable, distinct POD,
/// nonaliasing with the slot/queue. Absent/empty leave output untouched. The task
/// is removed before returning to Native payload/cache/coroutine effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_next_slot(
    slot: *mut *mut SchedulerQueue,
    output: *mut SchedulerTask,
) -> u32 {
    // SAFETY: per this function's `# Safety` contract, `slot` is live, aligned and initialized.
    let queue = unsafe { slot.read() };
    if queue.is_null() {
        return 0;
    }
    // SAFETY: `queue` is non-null (checked above), aligned and exclusive per the caller contract.
    match unsafe { &mut *queue }.pop() {
        Some(task) => {
            // SAFETY: per this function's `# Safety` contract, `output` is live, aligned and writable.
            unsafe { output.write(task) };
            2
        }
        None => 1,
    }
}
/// # Safety
/// Slot is exclusive and contains no remaining Native payloads. Native event wait
/// precedes this call in start. Drop Rust metadata then clear its sole cell at the
/// original publication point; null is a no-op. No Zend/payload destructor runs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_drop_slot(slot: *mut *mut SchedulerQueue) {
    // SAFETY: per this function's `# Safety` contract, `slot` is live, aligned and initialized.
    let queue = unsafe { slot.read() };
    if !queue.is_null() {
        // SAFETY: the slot's owned queue, with no remaining native payloads, dropped once.
        unsafe { SchedulerQueue::drop_owned(queue) };
        // SAFETY: as for the read above.
        unsafe { slot.write(std::ptr::null_mut()) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn absent_empty_fifo_counts_and_slot_reuse_are_one_owner() {
        let mut slot = std::ptr::null_mut();
        let mut out = SchedulerTask {
            token: 99,
            repetitions: 7,
        };
        unsafe {
            assert_eq!(
                swr_v1_phpcoroutines_scheduler_next_slot(&mut slot, &mut out),
                0
            );
            assert_eq!((out.token, out.repetitions), (99, 7));
            swr_v1_phpcoroutines_scheduler_drop_slot(&mut slot);
            assert_eq!(swr_v1_phpcoroutines_scheduler_prepare_slot(&mut slot), 1);
            let first = slot;
            assert_eq!(swr_v1_phpcoroutines_scheduler_prepare_slot(&mut slot), 1);
            assert_eq!(slot, first);
            assert_eq!(
                swr_v1_phpcoroutines_scheduler_next_slot(&mut slot, &mut out),
                1
            );
            assert_eq!((out.token, out.repetitions), (99, 7));
            for (token, count) in [(41, -2), (0, 0), (usize::MAX, 3)] {
                assert_eq!(
                    swr_v1_phpcoroutines_scheduler_try_push_slot(&mut slot, token, count),
                    1
                );
            }
            for expected in [(41, 0), (0, 0), (usize::MAX, 3)] {
                assert_eq!(
                    swr_v1_phpcoroutines_scheduler_next_slot(&mut slot, &mut out),
                    2
                );
                assert_eq!((out.token, out.repetitions), expected);
            }
            assert_eq!(
                swr_v1_phpcoroutines_scheduler_next_slot(&mut slot, &mut out),
                1
            );
            swr_v1_phpcoroutines_scheduler_drop_slot(&mut slot);
            assert!(slot.is_null());
            assert_eq!(
                swr_v1_phpcoroutines_scheduler_next_slot(&mut slot, &mut out),
                0
            );
        }
    }
}
