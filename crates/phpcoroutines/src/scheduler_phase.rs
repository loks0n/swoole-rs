//! Inline frontend admission/publication byte; Native owns its storage slot.
#[repr(C)]
pub struct SchedulerPhase {
    pub(crate) started: u8,
}

/// # Safety
/// State is live module-local inline zero-initialized POD: the private Scheduler
/// object's started slot or the protected frontend activated TLS/global slot.
/// Native allocation/constant initialization/storage/lifetime stay authoritative.
/// Reads may overlap reads as in the Native global fallback. Writes require
/// the original Native synchronization/owner scope; same-field racing writes
/// or read/write races remain outside that original defined contract. No
/// whole-state mutable reference is formed for a read.
/// no state borrow/frame spans callbacks, task creation, event wait or bailout.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_phase(
    state: *mut SchedulerPhase,
    operation: u32,
) -> u8 {
    match operation {
        0 => unsafe { std::ptr::read(std::ptr::addr_of!((*state).started)) },
        1 => {
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).started), 1) };
            1
        }
        2 => {
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).started), 0) };
            0
        }
        _ => 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_zero_seed_and_explicit_publication() {
        let mut state = SchedulerPhase { started: 0 };
        unsafe {
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 0), 0);
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 1), 1);
            // Admission reads do not clear the original sticky started state.
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 0), 1);
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 0), 1);
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 2), 0);
            assert_eq!(swr_v1_phpcoroutines_scheduler_phase(&mut state, 0), 0);
        }
    }
}
