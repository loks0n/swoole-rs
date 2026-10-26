//! Sole inline callback identities. Pointees and every effect remain Native.
use core::{cell::UnsafeCell, ptr};

#[repr(transparent)]
pub struct SwrPhpEventCallback {
    identity: UnsafeCell<usize>,
}

unsafe fn read(cell: *mut SwrPhpEventCallback) -> usize {
    unsafe { ptr::addr_of!((*cell).identity).cast::<usize>().read() }
}
unsafe fn write(cell: *mut SwrPhpEventCallback, identity: usize) {
    unsafe {
        ptr::addr_of_mut!((*cell).identity)
            .cast::<usize>()
            .write(identity)
    }
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
    unsafe {
        match mode {
            0 => {
                write(readable, new_read);
                write(writable, new_write);
                0
            }
            1 | 2 => {
                identity.write(read(if mode == 1 { readable } else { writable }));
                2
            }
            3 => match phase.read() {
                0 => {
                    identity.write(read(readable));
                    phase.write(1);
                    1
                }
                1 => {
                    identity.write(read(writable));
                    phase.write(2);
                    2
                }
                _ => 0,
            },
            _ => 0,
        }
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
    loop {
        let action = unsafe { crate::swr_v1_phpevents_update(phase, events, observation) };
        unsafe {
            match action {
                4 => observation = i64::from(new_read != 0),
                5 | 12 => observation = i64::from(read(readable) != 0),
                8 => observation = i64::from(new_write != 0),
                9 | 13 => observation = i64::from(read(writable) != 0),
                6 => {
                    identity.write(read(readable));
                    return action;
                }
                10 => {
                    identity.write(read(writable));
                    return action;
                }
                7 => write(readable, new_read),
                11 => write(writable, new_write),
                _ => return action,
            }
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
                    &mut phase,
                    0,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    11,
                    22,
                    &mut identity
                ),
                0
            );
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &mut identity
                ),
                1
            );
            assert_eq!(identity, 11);
            // Metadata-only change between steps: no destructor/callback runs.
            write(w.as_mut_ptr(), 33);
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &mut identity
                ),
                2
            );
            assert_eq!(identity, 33);
            assert_eq!(
                swr_v1_phpevents_callbacks(
                    &mut phase,
                    3,
                    r.as_mut_ptr(),
                    w.as_mut_ptr(),
                    0,
                    0,
                    &mut identity
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
                        &mut phase,
                        1536,
                        0,
                        &mut r,
                        &mut w,
                        33,
                        44,
                        &mut identity
                    ),
                    expected
                );
            }
            assert_eq!(identity, 11);
            assert_eq!(read(&mut r), 11);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &mut phase,
                    1536,
                    0,
                    &mut r,
                    &mut w,
                    33,
                    44,
                    &mut identity
                ),
                10
            );
            assert_eq!(read(&mut r), 33);
            assert_eq!(read(&mut w), 22);
            assert_eq!(identity, 22);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &mut phase,
                    1536,
                    0,
                    &mut r,
                    &mut w,
                    33,
                    44,
                    &mut identity
                ),
                14
            );
            assert_eq!(read(&mut w), 44);
            assert_eq!(
                swr_v1_phpevents_update_owned(
                    &mut phase,
                    1536,
                    0,
                    &mut r,
                    &mut w,
                    33,
                    44,
                    &mut identity
                ),
                1
            );
        }
    }
}
