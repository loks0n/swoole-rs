//! Sole inline callback identities. Pointees and every effect remain Native.
use core::cell::UnsafeCell;

#[repr(transparent)]
pub struct SwrPhpEventCallback {
    identity: UnsafeCell<usize>,
}

// The struct and its `UnsafeCell` are `repr(transparent)` over `usize`, so a cell
// pointer is also a pointer to its identity word.
unsafe fn read(cell: *mut SwrPhpEventCallback) -> usize {
    // SAFETY: the caller passes a non-null, aligned, initialized cell.
    unsafe { cell.cast::<usize>().read() }
}
unsafe fn write(cell: *mut SwrPhpEventCallback, identity: usize) {
    // SAFETY: the caller passes a non-null, aligned, writable cell.
    unsafe { cell.cast::<usize>().write(identity) }
}

/// Seed, obtain the invocation identity, or sequence the original two releases.
/// # Safety
/// Independent aligned cells and output must remain valid and nonoverlapping.
/// Seed accepts uninitialized cells; all other modes require initialized cells.
/// No Native effect runs in this function. FREE callers return after each
/// Native destruction; no slot is cleared and writable is read only on reentry.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_callbacks(
    phase: *mut u32,
    mode: u32,
    readable: *mut SwrPhpEventCallback,
    writable: *mut SwrPhpEventCallback,
    new_read: usize,
    new_write: usize,
    identity: *mut usize,
) -> u32 {
    if phase.is_null() || readable.is_null() || writable.is_null() || identity.is_null() {
        return 0;
    }
    // Every pointer is non-null (checked above), aligned, valid and disjoint per the
    // contract; cells are initialized in every mode except seed (0), which only writes.
    // SAFETY: as above.
    let get = |cell| unsafe { read(cell) };
    // SAFETY: as above.
    let set = |cell, value| unsafe { write(cell, value) };
    // SAFETY: as above.
    let publish = |value| unsafe { identity.write(value) };
    // SAFETY: as above.
    let set_phase = |value| unsafe { phase.write(value) };
    match mode {
        0 => {
            set(readable, new_read);
            set(writable, new_write);
            0
        }
        1 | 2 => {
            publish(get(if mode == 1 { readable } else { writable }));
            2
        }
        // SAFETY: as above.
        3 => match unsafe { phase.read() } {
            0 => {
                publish(get(readable));
                set_phase(1);
                1
            }
            1 => {
                publish(get(writable));
                set_phase(2);
                2
            }
            _ => 0,
        },
        _ => 0,
    }
}

/// Existing update protocol over the sole persistent identity pair.
/// # Safety
/// Same cell obligations as callbacks; phase starts0. Constructor identities
/// are exact Native outputs. Native deferral/backend effects finish before the
/// next call; no borrow is retained. Observation is the Native backend status.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_update_owned(
    phase: *mut u32,
    events: i64,
    mut observation: i64,
    readable: *mut SwrPhpEventCallback,
    writable: *mut SwrPhpEventCallback,
    new_read: usize,
    new_write: usize,
    identity: *mut usize,
) -> u32 {
    if phase.is_null() || readable.is_null() || writable.is_null() || identity.is_null() {
        return 0;
    }
    // Non-null (checked above), aligned, initialized, disjoint cells and output per the
    // contract.
    // SAFETY: as above.
    let get = |cell| unsafe { read(cell) };
    // SAFETY: as above.
    let set = |cell, value| unsafe { write(cell, value) };
    // SAFETY: as above.
    let publish = |value| unsafe { identity.write(value) };
    loop {
        // SAFETY: `phase` is the caller's non-null phase word, starting at 0.
        let action = unsafe { crate::swr_v1_phpevents_update(phase, events, observation) };
        match action {
            4 => observation = i64::from(new_read != 0),
            5 | 12 => observation = i64::from(get(readable) != 0),
            8 => observation = i64::from(new_write != 0),
            9 | 13 => observation = i64::from(get(writable) != 0),
            6 => {
                publish(get(readable));
                return action;
            }
            10 => {
                publish(get(writable));
                return action;
            }
            7 => set(readable, new_read),
            11 => set(writable, new_write),
            _ => return action,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use core::mem::{MaybeUninit, align_of, size_of};
    #[test]
    fn inline_pair_tokens_and_fresh_release_observation() {
        assert_eq!(size_of::<SwrPhpEventCallback>(), size_of::<usize>());
        assert_eq!(align_of::<SwrPhpEventCallback>(), align_of::<usize>());
        let mut r = MaybeUninit::<SwrPhpEventCallback>::uninit();
        let mut w = MaybeUninit::<SwrPhpEventCallback>::uninit();
        let (mut phase, mut identity) = (0, 0);
        unsafe {
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &raw mut phase,
                    0,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    11,
                    22,
                    &raw mut identity
                ),
                0
            );
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &raw mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &raw mut identity
                ),
                1
            );
            assert_eq!(identity, 11);
            // Metadata-only change between steps: no destructor/callback runs.
            write(w.as_mut_ptr(), 33);
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &raw mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &raw mut identity
                ),
                2
            );
            assert_eq!(identity, 33);
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &raw mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &raw mut identity
                ),
                0
            );
            assert_eq!(read(r.as_mut_ptr()), 11);
            assert_eq!(read(w.as_mut_ptr()), 33);
        }
    }
    #[test]
    fn update_publication_follows_completed_effect_boundary() {
        let mut r = SwrPhpEventCallback {
            identity: UnsafeCell::new(11),
        };
        let mut w = SwrPhpEventCallback {
            identity: UnsafeCell::new(22),
        };
        let (mut phase, mut identity) = (0, 0);
        unsafe {
            for expected in [2, 3, 6] {
                assert_eq!(
                    swr_v1_phpevents_update_owned(
                        &raw mut phase,
                        1536,
                        0,
                        &raw mut r,
                        &raw mut w,
                        33,
                        44,
                        &raw mut identity
                    ),
                    expected
                );
            }
            assert_eq!(identity, 11);
            assert_eq!(read(&raw mut r), 11);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &raw mut phase,
                    1536,
                    0,
                    &raw mut r,
                    &raw mut w,
                    33,
                    44,
                    &raw mut identity
                ),
                10
            );
            assert_eq!(read(&raw mut r), 33);
            assert_eq!(read(&raw mut w), 22);
            assert_eq!(identity, 22);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &raw mut phase,
                    1536,
                    0,
                    &raw mut r,
                    &raw mut w,
                    33,
                    44,
                    &raw mut identity
                ),
                14
            );
            assert_eq!(read(&raw mut w), 44);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &raw mut phase,
                    1536,
                    0,
                    &raw mut r,
                    &raw mut w,
                    33,
                    44,
                    &raw mut identity
                ),
                1
            );
        }
    }
}
