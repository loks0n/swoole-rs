//! Constructor/reserve allocation requests; native effects and live object
//! publication happen only after the plan returns.
use super::{INVALID, OK, StringState, aligned};

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct StringAllocationPlan {
    pub capacity: usize,
    /// Native malloc=1 or realloc=2; zero on error.
    pub action: u32,
}

/// Initial allocation=0 never reads source (constructor fields may be uninitialized).
/// Reserve=1 validates an independent initialized snapshot, then selects initial
/// allocation for zero capacity or realloc otherwise. No pointer bytes are read.
/// # Safety
/// Output is writable/aligned and disjoint. For reserve, source is a readable,
/// aligned independent POD. No native callbacks, allocation, retained pointers,
/// or object-layout access occurs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_allocation_plan(
    operation: u32,
    source: *const StringState,
    requested: usize,
    alignment: usize,
    output: *mut StringAllocationPlan,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let calculate = || {
        let capacity = aligned(requested, alignment)?;
        let action = match operation {
            0 => 1,
            1 if !source.is_null() => {
                // SAFETY: non-null (checked above), valid, aligned POD.
                let state = unsafe { *source };
                state.validate()?;
                if capacity < state.length {
                    return Err(INVALID);
                }
                if state.capacity == 0 { 1 } else { 2 }
            }
            _ => return Err(INVALID),
        };
        Ok(StringAllocationPlan { capacity, action })
    };
    let (status, result) = match calculate() {
        Ok(result) => (OK, result),
        Err(status) => (status, StringAllocationPlan::default()),
    };
    // SAFETY: `output` is non-null (checked above), aligned, writable and disjoint.
    unsafe { output.write(result) };
    status
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn initial_and_reserve_choose_native_effect_without_touching_bytes() {
        let mut bytes = [0x5au8; 64];
        let mut result = StringAllocationPlan::default();
        for requested in [1, 7, 8, 9, 16, 63, 64, 65] {
            assert_eq!(
                unsafe {
                    swr_v1_string_allocation_plan(0, std::ptr::null(), requested, 8, &mut result)
                },
                OK
            );
            assert_eq!((result.capacity, result.action), ((requested + 7) & !7, 1));
            for capacity in [0, 64] {
                let state = StringState {
                    data: if capacity == 0 {
                        std::ptr::null_mut()
                    } else {
                        bytes.as_mut_ptr()
                    },
                    length: 0,
                    capacity,
                    offset: 0,
                };
                assert_eq!(
                    unsafe { swr_v1_string_allocation_plan(1, &state, requested, 8, &mut result) },
                    OK
                );
                assert_eq!(
                    (result.capacity, result.action),
                    ((requested + 7) & !7, if capacity == 0 { 1 } else { 2 })
                );
            }
        }
        assert_eq!(bytes, [0x5a; 64]);
    }
    #[test]
    fn invalid_or_truncated_storage_is_refused_before_effect() {
        let mut bytes = [0u8; 32];
        let state = StringState {
            data: bytes.as_mut_ptr(),
            length: 17,
            capacity: 32,
            offset: 1,
        };
        let mut out = StringAllocationPlan {
            capacity: 99,
            action: 99,
        };
        for (op, source, size, alignment) in [
            (99, &state as *const _, 32, 8),
            (1, std::ptr::null(), 32, 8),
            (1, &state, 8, 8),
            (0, std::ptr::null(), 32, 3),
            (0, std::ptr::null(), usize::MAX, 8),
        ] {
            assert!(
                unsafe { swr_v1_string_allocation_plan(op, source, size, alignment, &mut out) } < 0
            );
            assert_eq!((out.capacity, out.action), (0, 0));
        }
        assert_eq!(
            unsafe {
                swr_v1_string_allocation_plan(0, std::ptr::null(), 8, 8, std::ptr::null_mut())
            },
            INVALID
        );
    }
}
