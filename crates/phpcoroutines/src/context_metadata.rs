//! Sole logical custody of primitive frontend cells at Native PHPContext offsets.
use crate::scheduler_phase::SchedulerPhase;
use std::ffi::{c_int, c_long};

#[repr(C)]
pub struct ErrorCell {
    pub value: c_int,
}
#[repr(C)]
pub struct ParentCell {
    pub value: c_long,
}
#[repr(C)]
pub struct ClockCell {
    pub value: i64,
}

/// Native forms addresses only; Rust never interprets a PHPContext or Zend value.
/// Null cells denote absent/unused fields, not an alternate registry.
#[repr(C)]
pub struct ContextCells {
    pub silence: *mut SchedulerPhase,
    pub scheduler: *mut SchedulerPhase,
    pub original: *mut ErrorCell,
    pub temporary: *mut ErrorCell,
    pub notified: *mut SchedulerPhase,
    pub parent: *mut ParentCell,
    pub clock: *mut ClockCell,
}
#[repr(C)]
pub struct MetadataPlan {
    pub action: u32,
    pub value: i64,
}

/// # Safety
/// Cells is an immutable local address descriptor. Only the cells used by kind
/// must be valid and initialized before a read; initialization operations write
/// without reading. Native owns physical slots/lifetime and synchronization.
/// Raw per-cell accesses preserve disjoint-field and aliased read observations.
/// Stage is exclusive invocation-local zeroed POD. Observation is the requested
/// fresh error-mask/clock fact. No borrow/frame survives Native effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_metadata(
    stage: *mut u32,
    kind: u32,
    cells: *const ContextCells,
    observation: i64,
    limit: u8,
) -> MetadataPlan {
    // SAFETY: per this function's `# Safety` contract, `cells` is live, aligned and initialized.
    let cells = unsafe { &*cells };
    // SAFETY: per this function's `# Safety` contract, `stage` is live, aligned and exclusive.
    let stage = unsafe { &mut *stage };
    let current = *stage;
    *stage = current.saturating_add(1);
    let mut plan = MetadataPlan {
        action: 0,
        value: 0,
    };
    match kind {
        0 => match current {
            // begin silence: flag before fresh Native mask
            0 => {
                // SAFETY: this kind's cells are valid and initialized (see the contract).
                unsafe { (*cells.silence).started = 1 };
                plan.action = 1;
            }
            // SAFETY: this kind's cells are valid and initialized (see the contract).
            1 => unsafe { (*cells.original).value = observation as c_int },
            _ => (),
        },
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        1 => unsafe { (*cells.silence).started = 0 },
        2 => match current {
            // save: temporary before original-mask restoration
            // SAFETY: this kind's cells are valid and initialized (see the contract).
            0 if unsafe { (*cells.silence).started != 0 } => plan.action = 1,
            1 => {
                // SAFETY: this kind's cells are valid and initialized (see the contract).
                unsafe { (*cells.temporary).value = observation as c_int };
                plan = MetadataPlan {
                    action: 2,
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    value: unsafe { (*cells.original).value }.into(),
                };
            }
            _ => (),
        },
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        3 if current == 0 && unsafe { (*cells.silence).started != 0 } => {
            plan = MetadataPlan {
                action: 2,
                // SAFETY: this kind's cells are valid and initialized (see the contract).
                value: unsafe { (*cells.temporary).value }.into(),
            };
        }
        4 | 5 => {
            // toggle only a present, initialized task cell
            if !cells.scheduler.is_null() {
                let requested = u8::from(kind == 4);
                // SAFETY: this kind's cells are valid and initialized (see the contract).
                if unsafe { (*cells.scheduler).started } != requested {
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    unsafe { (*cells.scheduler).started = requested };
                    plan.value = 1;
                }
            }
        }
        6 => match current {
            // SAFETY: this kind's cells are valid and initialized (see the contract).
            0 if unsafe { (*cells.scheduler).started != 0 } => plan.action = 3,
            0 => plan.action = 4,
            1 => {
                // clock already observed; only now read saved last_msec
                plan.action = if i128::from(observation)
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    - i128::from(unsafe { (*cells.clock).value })
                    > i128::from(limit)
                {
                    5
                } else {
                    4
                };
            }
            _ => (),
        },
        7 => {
            if !cells.parent.is_null() {
                // c_long width is a Native ABI property (32/64 bits), not the
                // Rust target pointer width. Captured SDK checks the cell layout.
                #[expect(
                    clippy::unnecessary_cast,
                    reason = "c_long is i64 on the supported 64-bit targets"
                )]
                {
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    plan.value = unsafe { (*cells.parent).value } as i64;
                }
            }
        }
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        8 => unsafe { (*cells.parent).value = observation as c_long },
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        9 => unsafe { (*cells.clock).value = observation },
        10 => {
            // whole fiber switch policy; internal flag steps never escape
            *stage = current;
            let mut fact = observation;
            loop {
                // SAFETY: `stage` is this call's exclusive, zeroed POD; no context is passed.
                let action = unsafe {
                    crate::fiber::swr_v1_phpcoroutines_fiber(stage, 1, fact, std::ptr::null())
                };
                match action {
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    10 => fact = i64::from(unsafe { (*cells.notified).started }),
                    // SAFETY: this kind's cells are valid and initialized (see the contract).
                    14 => unsafe { (*cells.notified).started = 1 },
                    _ => {
                        plan.action = action;
                        break;
                    }
                }
            }
        }
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        11 => unsafe { (*cells.scheduler).started = 1 }, // first publication, no read
        // SAFETY: this kind's cells are valid and initialized (see the contract).
        12 => unsafe { (*cells.notified).started = 1 }, // main-context initialization, no read
        _ => (),
    }
    if plan.action == 0 {
        *stage = u32::MAX;
    }
    plan
}

#[cfg(test)]
mod tests {
    use super::*;
    fn empty() -> ContextCells {
        ContextCells {
            silence: std::ptr::null_mut(),
            scheduler: std::ptr::null_mut(),
            original: std::ptr::null_mut(),
            temporary: std::ptr::null_mut(),
            notified: std::ptr::null_mut(),
            parent: std::ptr::null_mut(),
            clock: std::ptr::null_mut(),
        }
    }
    #[test]
    fn silence_write_only_initialization_and_error_mask_order() {
        let mut flag = SchedulerPhase { started: 0 };
        let mut original = std::mem::MaybeUninit::<ErrorCell>::uninit();
        let mut temporary = std::mem::MaybeUninit::<ErrorCell>::uninit();
        let cells = ContextCells {
            silence: &mut flag,
            original: original.as_mut_ptr(),
            temporary: temporary.as_mut_ptr(),
            ..empty()
        };
        unsafe {
            let mut stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 0, &cells, 0, 0).action,
                1
            );
            assert_eq!(flag.started, 1); // before the Native mask observation
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 0, &cells, -17, 0).action,
                0
            );
            assert_eq!((*cells.original).value, -17);
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 2, &cells, 0, 0).action,
                1
            );
            let result = swr_v1_phpcoroutines_metadata(&mut stage, 2, &cells, 23, 0);
            assert_eq!((result.action, result.value), (2, -17));
            assert_eq!((*cells.temporary).value, 23);
            stage = 0;
            let result = swr_v1_phpcoroutines_metadata(&mut stage, 3, &cells, 0, 0);
            assert_eq!((result.action, result.value), (2, 23));
            stage = 0;
            swr_v1_phpcoroutines_metadata(&mut stage, 1, &cells, 0, 0);
            assert_eq!(flag.started, 0);
            // Disabled silence must not access either uninitialized mask cell.
            let cells = ContextCells {
                silence: &mut flag,
                ..empty()
            };
            for kind in [2, 3] {
                stage = 0;
                assert_eq!(
                    swr_v1_phpcoroutines_metadata(&mut stage, kind, &cells, 0, 0).action,
                    0
                );
            }
        }
    }
    #[test]
    fn scheduling_lineage_clock_and_fiber_publications() {
        unsafe {
            let mut stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 4, &empty(), 0, 0).value,
                0
            );
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 7, &empty(), 0, 0).value,
                0
            );
            let mut flag = SchedulerPhase { started: 0 };
            let mut cells = ContextCells {
                scheduler: &mut flag,
                ..empty()
            };
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 6, &cells, 0, 10).action,
                4
            ); // no clock pointer/read
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 4, &cells, 0, 0).value,
                1
            );
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 4, &cells, 0, 0).value,
                0
            );
            let mut clock = ClockCell { value: 100 };
            cells.clock = &mut clock;
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 6, &cells, 0, 10).action,
                3
            );
            clock.value = 105; // fresh cell read only after Native clock access
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 6, &cells, 115, 10).action,
                4
            );
            stage = 0;
            swr_v1_phpcoroutines_metadata(&mut stage, 9, &cells, -3, 0);
            assert_eq!(clock.value, -3);
            let mut parent = std::mem::MaybeUninit::<ParentCell>::uninit();
            cells.parent = parent.as_mut_ptr();
            stage = 0;
            swr_v1_phpcoroutines_metadata(&mut stage, 8, &cells, -8, 0);
            stage = 0;
            assert_eq!(
                swr_v1_phpcoroutines_metadata(&mut stage, 7, &cells, 0, 0).value,
                -8
            );
            let mut notified = SchedulerPhase { started: 0 };
            cells.notified = &mut notified;
            for expected in [vec![8, 9, 11, 12, 13], vec![8, 9, 12]] {
                stage = 0;
                let mut actual = Vec::new();
                loop {
                    let result = swr_v1_phpcoroutines_metadata(&mut stage, 10, &cells, 0, 0);
                    if result.action == 0 {
                        break;
                    }
                    actual.push(result.action);
                    if result.action == 13 {
                        assert_eq!(notified.started, 0);
                    }
                }
                assert_eq!(actual, expected);
                assert_eq!(notified.started, 1);
            }
            let mut seed = std::mem::MaybeUninit::<SchedulerPhase>::uninit();
            cells.scheduler = seed.as_mut_ptr();
            stage = 0;
            swr_v1_phpcoroutines_metadata(&mut stage, 11, &cells, 0, 0);
            assert_eq!((*cells.scheduler).started, 1);
            cells.notified = seed.as_mut_ptr();
            stage = 0;
            swr_v1_phpcoroutines_metadata(&mut stage, 12, &cells, 0, 0);
            assert_eq!((*cells.notified).started, 1);
        }
    }
}
