//! Sole inline timing words. Native clocks are sampled before entering Rust.
use core::ffi::c_long;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CoroutineTiming {
    pub init_msec: c_long,
    pub switch_usec: c_long,
    pub execute_usec: c_long,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_coroutine_timing_new(init_msec: c_long, now: c_long) -> CoroutineTiming {
    CoroutineTiming {
        init_msec,
        switch_usec: now,
        execute_usec: 0,
    }
}

/// # Safety
/// Each non-null pointer addresses a live aligned timing record accessible on
/// this thread. The two pointers may alias; the first exclusive borrow ends
/// before the second pointer is accessed. No borrow is retained after return.
/// Native signed arithmetic must be defined; wrapping outside that domain is
/// deterministic but is not a compatibility claim for undefined C++ inputs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_timing_switch(
    yielding: *mut CoroutineTiming,
    resuming: *mut CoroutineTiming,
    now: c_long,
) {
    if let Some(yielding) = unsafe { yielding.as_mut() } {
        let delta = now.wrapping_sub(yielding.switch_usec);
        yielding.execute_usec = yielding.execute_usec.wrapping_add(delta);
    }
    // The first exclusive borrow ends before observing this possibly same cell.
    if let Some(resuming) = unsafe { resuming.as_mut() } {
        resuming.switch_usec = now;
    }
}

/// # Safety
/// `timing` addresses a live aligned readable timing record. No simultaneous
/// mutation may race this call. Native arithmetic must be defined.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_timing_usage(
    timing: *const CoroutineTiming,
    now: c_long,
) -> c_long {
    let timing = unsafe { &*timing };
    now.wrapping_sub(timing.switch_usec)
        .wrapping_add(timing.execute_usec)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn alias_updates_elapsed_before_switch_and_readers_do_not_mutate() {
        let mut record = swr_v1_coroutine_timing_new(7, 10);
        let pointer = &raw mut record;
        unsafe {
            swr_v1_coroutine_timing_switch(pointer, pointer, 30);
        }
        assert_eq!(
            record,
            CoroutineTiming {
                init_msec: 7,
                switch_usec: 30,
                execute_usec: 20
            }
        );
        assert_eq!(unsafe { swr_v1_coroutine_timing_usage(pointer, 39) }, 29);
        assert_eq!(record.execute_usec, 20);
    }
    #[test]
    fn distinct_null_and_negative_defined_deltas() {
        let mut a = swr_v1_coroutine_timing_new(1, 90);
        let mut b = swr_v1_coroutine_timing_new(2, 20);
        unsafe {
            swr_v1_coroutine_timing_switch(&raw mut a, &raw mut b, 80);
            swr_v1_coroutine_timing_switch(core::ptr::null_mut(), &raw mut b, 110);
            swr_v1_coroutine_timing_switch(core::ptr::null_mut(), core::ptr::null_mut(), 0);
        }
        assert_eq!(a.execute_usec, -10);
        assert_eq!(a.switch_usec, 90);
        assert_eq!(b.switch_usec, 110);
        assert_eq!(b.execute_usec, 0);
        assert_eq!(
            unsafe { swr_v1_coroutine_timing_usage(&raw const a, 85) },
            -15
        );
        assert_eq!(
            core::mem::size_of::<CoroutineTiming>(),
            3 * core::mem::size_of::<c_long>()
        );
        assert_eq!(
            core::mem::align_of::<CoroutineTiming>(),
            core::mem::align_of::<c_long>()
        );
    }
}
