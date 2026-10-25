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

unsafe fn load(state: *mut InterruptState) -> u8 {
    unsafe { AtomicU8::from_ptr((*state).running.get()).load(Ordering::Relaxed) }
}
unsafe fn store(state: *mut InterruptState, value: u8) {
    unsafe { AtomicU8::from_ptr((*state).running.get()).store(value, Ordering::Relaxed) };
}

/// # Safety
/// State is the live, constant-zero-seeded Native TLS/global one-byte cell; all
/// runtime access uses this atomic API. Stage is distinct exclusive local POD,
/// initially zero. Kind/max_exec are fixed. The child passes its OWN Native TLS
/// lookup, not a captured parent's address. No Rust frame/borrow spans Native
/// threads, VM stores, signal masking, clock reads, sleeps or joins. Relaxed
/// accesses do not assert additional Native synchronization or undefined-race
/// parity. No Rust Send/Sync promise is added for the surrounding Native state.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_interrupt(
    state: *mut InterruptState,
    stage: *mut u32,
    kind: u32,
    max_exec: u8,
) -> InterruptPlan {
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
                0 if unsafe { load(state) } == 0 => 1,
                1 => {
                    unsafe { store(state, 1) };
                    2
                }
                _ => 0,
            },
            1 => match current {
                0 if unsafe { load(state) } != 0 => {
                    unsafe { store(state, 0) };
                    3
                }
                _ => 0,
            },
            2 => match current {
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
