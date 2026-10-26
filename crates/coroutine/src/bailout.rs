//! Complete bailout admission and authoritative foreign-origin walk. Native
//! std::function, errors, yield and exit are effects after this frame returns.
use crate::CoroutineIdentity;
use core::ffi::c_void;

#[repr(C)]
pub struct CoroutineBailoutCursor {
    pub saved: *mut c_void,
    pub phase: u32,
}
#[repr(C)]
pub struct CoroutineBailoutAction {
    pub action: u32,
    pub coroutine: *mut c_void,
}

/// # Safety
/// Cursor is initialized exclusive caller-local storage, phase0 initially.
/// Current is an initialized readable identity cell at phase0 only. Native
/// observes function presence only when requested, and executes its assignment
/// before phase2. Saved tokens retain original live foreign allocation
/// provenance. At phase2 every reached object has an aligned initialized
/// CoroutineIdentity at the exact Native-derived origin_offset, within that
/// allocation and with representable in-bounds byte arithmetic. Only this
/// designated cell may be addressed; no other object bytes are accessed. The
/// original chain terminates with null and is serialized during this call.
/// No Rust frame or reference survives a Native callable/effect boundary.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_bailout_step(
    cursor: *mut CoroutineBailoutCursor,
    current: *const CoroutineIdentity,
    function_present: u8,
    origin_offset: usize,
) -> CoroutineBailoutAction {
    // SAFETY: per this function's `# Safety` contract, `cursor` is live, aligned and exclusive.
    let cursor = unsafe { &mut *cursor };
    let action = match cursor.phase {
        0 => {
            // SAFETY: per this function's `# Safety` contract, `current` is live, aligned and initialized.
            cursor.saved = unsafe { (*current).token };
            if cursor.saved.is_null() {
                cursor.phase = 3;
                0 // Original default Native callback assignment then return.
            } else {
                cursor.phase = 1;
                1 // Observe supplied function only on the nonnull path.
            }
        }
        1 => {
            cursor.phase = 2;
            if function_present == 0 { 2 } else { 3 }
        }
        2 => {
            let mut object = cursor.saved;
            loop {
                // Explicit foreign-field contract: original object provenance,
                // forward offset to ONE initialized repr(C) cell, raw read.
                // SAFETY: `object` is a live chain member with an initialized identity cell at
                // `origin_offset` (see the contract); the chain is serialized.
                let origin = unsafe { origin_at(object, origin_offset) };
                if origin.is_null() {
                    break;
                }
                // Original while-test and assignment observe the parent twice.
                // SAFETY: as above.
                object = unsafe { origin_at(object, origin_offset) };
            }
            cursor.saved = object;
            cursor.phase = 3;
            4 // Native root yield and exit; no subsequent object observation.
        }
        _ => 5,
    };
    CoroutineBailoutAction {
        action,
        coroutine: cursor.saved,
    }
}

// The only foreign address calculation: designated cell, never whole object.
unsafe fn origin_at(object: *mut c_void, offset: usize) -> *mut c_void {
    // SAFETY: the caller guarantees an initialized, aligned identity cell at `offset`
    // inside `object`'s allocation; only that cell is read.
    unsafe {
        object
            .cast::<u8>()
            .wrapping_add(offset)
            .cast::<CoroutineIdentity>()
            .read()
            .token
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use core::{mem::offset_of, ptr};
    #[repr(C)]
    struct Foreign {
        padding: [usize; 3],
        origin: CoroutineIdentity,
        tail: usize,
    }
    #[test]
    fn complete_walk_uses_saved_object_and_fresh_cells_after_copy_barrier() {
        let mut root = Foreign {
            padding: [11; 3],
            origin: CoroutineIdentity {
                token: ptr::null_mut(),
            },
            tail: 99,
        };
        let mut middle = Foreign {
            padding: [22; 3],
            origin: CoroutineIdentity {
                token: ptr::from_mut(&mut root).cast(),
            },
            tail: 88,
        };
        let mut leaf = Foreign {
            padding: [33; 3],
            origin: CoroutineIdentity {
                token: ptr::from_mut(&mut middle).cast(),
            },
            tail: 77,
        };
        let mut current = CoroutineIdentity {
            token: ptr::from_mut(&mut leaf).cast(),
        };
        let mut cursor = CoroutineBailoutCursor {
            saved: ptr::null_mut(),
            phase: 0,
        };
        unsafe {
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, &current, 0, 0).action,
                1
            );
            current.token = ptr::null_mut(); // Saved snapshot, not fresh current.
            assert!(current.token.is_null());
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, ptr::null(), 1, 0).action,
                3
            );
            // Metadata-only copy-barrier witness: fresh links after effects.
            middle.origin.token = ptr::null_mut();
            let final_step = swr_v1_coroutine_bailout_step(
                &mut cursor,
                ptr::null(),
                0,
                offset_of!(Foreign, origin),
            );
            assert_eq!(final_step.action, 4);
            assert_eq!(final_step.coroutine, ptr::from_mut(&mut middle).cast());
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, ptr::null(), 0, usize::MAX).action,
                5
            );
            assert_eq!(leaf.tail, 77);
            assert_eq!(middle.tail, 88);
            assert_eq!(root.tail, 99);
        }
    }
    #[test]
    fn null_current_never_reads_other_inputs_and_missing_function_keeps_original_copy_order() {
        let current = CoroutineIdentity {
            token: ptr::null_mut(),
        };
        let mut cursor = CoroutineBailoutCursor {
            saved: ptr::null_mut(),
            phase: 0,
        };
        unsafe {
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, &current, 0, usize::MAX).action,
                0
            );
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, ptr::null(), 0, usize::MAX).action,
                5
            );
        }
        // This is only the admission descriptor; the Native fatal effect is NOT run.
        let mut byte = 0;
        let current = CoroutineIdentity {
            token: ptr::from_mut(&mut byte).cast(),
        };
        cursor.phase = 0;
        unsafe {
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, &current, 0, 0).action,
                1
            );
            assert_eq!(
                swr_v1_coroutine_bailout_step(&mut cursor, ptr::null(), 0, 0).action,
                2
            );
        }
    }
}
