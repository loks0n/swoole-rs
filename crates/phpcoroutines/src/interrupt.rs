//! Sole interrupt flag and complete start/stop/loop policy. Effects stay Native.
use std::cell::UnsafeCell;
use std::sync::atomic::{AtomicU8, Ordering};

#[repr(C)]
pub struct InterruptState {
    running: UnsafeCell<u8>,
}
#[repr(C)]
pub struct InterruptPlan {
    pub action: u32,
    pub value: u64,
}

// The running cell, viewed atomically. Callers pass the live, zero-seeded native cell,
// which every runtime access treats as `std::atomic_bool`.
unsafe fn running<'a>(state: *mut InterruptState) -> &'a AtomicU8 {
    // SAFETY: `state` is live for the call (see above).
    let cell = unsafe { &(*state).running };
    // SAFETY: the cell is aligned for `u8` and only ever accessed atomically.
    unsafe { AtomicU8::from_ptr(cell.get()) }
}
unsafe fn load(state: *mut InterruptState) -> u8 {
    // SAFETY: forwards the caller's live cell.
    unsafe { running(state) }.load(Ordering::Acquire)
}
unsafe fn store(state: *mut InterruptState, value: u8) {
    // SAFETY: forwards the caller's live cell.
    unsafe { running(state) }.store(value, Ordering::Release);
}

/// # Safety
/// State is the live, constant-zero-seeded Native TLS/global one-byte cell; all
/// runtime access uses this atomic API. Stage is distinct exclusive local POD,
/// initially zero. Kind/max_exec are fixed. The helper thread passes the cell of
/// the thread that started it, captured at start (upstream 7e6a4397a), so it
/// outlives the helper until stop joins it. Acquire loads and release stores
/// match upstream's std::atomic_bool. No Rust frame/borrow spans Native threads,
/// VM stores, signal masking, clock reads, sleeps or joins. No Rust Send/Sync
/// promise is added for the surrounding Native state.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_interrupt(
    state: *mut InterruptState,
    stage: *mut u32,
    kind: u32,
    max_exec: u8,
) -> InterruptPlan {
    // SAFETY: per this function's `# Safety` contract, `stage` is live, aligned and exclusive.
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        let mut plan = InterruptPlan {
            action: 0,
            value: 0,
        };
        plan.action = match kind {
            0 => match current {
                // SAFETY: `state` is the live native interrupt cell (see the contract).
                0 if unsafe { load(state) } == 0 => 1,
                1 => {
                    // SAFETY: `state` is the live native interrupt cell (see the contract).
                    unsafe { store(state, 1) };
                    2
                }
                _ => 0,
            },
            1 => match current {
                // SAFETY: `state` is the live native interrupt cell (see the contract).
                0 if unsafe { load(state) } != 0 => {
                    // SAFETY: `state` is the live native interrupt cell (see the contract).
                    unsafe { store(state, 0) };
                    3
                }
                _ => 0,
            },
            2 => match current {
                // SAFETY: `state` is the live native interrupt cell (see the contract).
                0 if unsafe { load(state) } != 0 => 4,
                1 => {
                    plan.value = u64::from(max_exec / 2);
                    5
                }
                2 => {
                    *stage = 0;
                    continue;
                }
                _ => 0,
            },
            3 => match current {
                // SAFETY: `state` is the live native interrupt cell (see the contract).
                0 if unsafe { load(state) } != 0 => 6,
                _ => 0,
            },
            _ => 0,
        };
        if plan.action == 0 {
            *stage = u32::MAX;
        }
        return plan;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn state() -> InterruptState {
        InterruptState {
            running: UnsafeCell::new(0),
        }
    }
    unsafe fn record(state: *mut InterruptState) -> u32 {
        unsafe { swr_v1_phpcoroutines_interrupt(state, &mut 0, 3, 10).action }
    }
    #[test]
    fn constant_seed_start_publication_stop_and_record_are_sole_state() {
        assert_eq!(std::mem::size_of::<InterruptState>(), 1);
        assert_eq!(std::mem::align_of::<InterruptState>(), 1);
        let mut state = state();
        unsafe {
            assert_eq!(record(&mut state), 0);
            let mut start = 0;
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut start, 0, 10).action,
                1
            );
            assert_eq!(record(&mut state), 0); // VM publication must happen first
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut start, 0, 10).action,
                2
            );
            assert_eq!(record(&mut state), 6);
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut start, 0, 10).action,
                0
            );
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut 0, 0, 10).action,
                0
            );
            let mut stop = 0;
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut stop, 1, 10).action,
                3
            );
            assert_eq!(record(&mut state), 0); // false before Native join
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut stop, 1, 10).action,
                0
            );
            assert_eq!(
                swr_v1_phpcoroutines_interrupt(&mut state, &mut 0, 1, 10).action,
                0
            );
        }
    }
    #[test]
    fn loop_rechecks_after_sleep_and_uses_its_own_scope() {
        for maximum in [0, 1, 2, 9, 10, 255] {
            let mut parent = state();
            let mut child = state();
            unsafe {
                store(&mut parent, 1);
                assert_eq!(
                    swr_v1_phpcoroutines_interrupt(&mut child, &mut 0, 2, maximum).action,
                    0
                );
                store(&mut child, 1);
                let mut stage = 0;
                for _ in 0..3 {
                    assert_eq!(
                        swr_v1_phpcoroutines_interrupt(&mut child, &mut stage, 2, maximum).action,
                        4
                    );
                    let sleep = swr_v1_phpcoroutines_interrupt(&mut child, &mut stage, 2, maximum);
                    assert_eq!((sleep.action, sleep.value), (5, u64::from(maximum) / 2));
                }
                store(&mut child, 0);
                assert_eq!(
                    swr_v1_phpcoroutines_interrupt(&mut child, &mut stage, 2, maximum).action,
                    0
                );
                assert_eq!(record(&mut parent), 6); // no implicit parent lookup
            }
        }
    }
}
