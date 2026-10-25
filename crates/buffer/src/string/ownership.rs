//! Operation-local ownership policy. Native free/copy/move effects run after
//! return; neither native allocation bytes nor allocator callbacks enter Rust.
use super::{INVALID, OK};
use std::ptr;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct StringOwnershipPlan {
    pub owner: *mut u8,
    pub actions: u64,
}

/// Dispose=0, copy assignment=1, move assignment=2. Actions are low byte first:
/// native free=1, copy=2, move=3. Native object metadata remains unchanged until
/// the native effect executes, matching original callback observation order.
/// A self-assignment has no effect, even when an owned allocation is present.
///
/// # Safety
/// Non-null output points to one writable aligned plan. Owner is only an opaque
/// native token, never dereferenced or retained. No allocation/callback occurs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_ownership_plan(
    operation: u32,
    same_object: u8,
    has_allocator: u8,
    owner: *mut u8,
    output: *mut StringOwnershipPlan,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let mut plan = StringOwnershipPlan {
        owner: ptr::null_mut(),
        actions: 0,
    };
    let status = if operation > 2 {
        INVALID
    } else if operation != 0 && same_object != 0 {
        OK
    } else {
        let owned = has_allocator != 0 && !owner.is_null();
        if owned {
            plan.owner = owner;
            plan.actions = 1;
        }
        let next = match operation {
            1 => 2,
            2 => 3,
            _ => 0,
        };
        plan.actions |= next << if owned { 8 } else { 0 };
        OK
    };
    // SAFETY: output is the caller's independent writable POD for this call.
    unsafe { output.write(plan) };
    status
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ownership_and_continuation_cover_native_order_without_byte_access() {
        let mut live = [0x5au8; 8];
        for operation in 0..3 {
            for same in [0, 1, u8::MAX] {
                for allocator in [0, 1, u8::MAX] {
                    for owner in [ptr::null_mut(), live.as_mut_ptr()] {
                        let mut result = StringOwnershipPlan {
                            owner: live.as_mut_ptr(),
                            actions: u64::MAX,
                        };
                        assert_eq!(
                            unsafe {
                                swr_v1_string_ownership_plan(
                                    operation,
                                    same,
                                    allocator,
                                    owner,
                                    &mut result,
                                )
                            },
                            OK
                        );
                        let mut expected = Vec::new();
                        if operation == 0 || same == 0 {
                            if allocator != 0 && !owner.is_null() {
                                expected.push(1);
                            }
                            if operation == 1 {
                                expected.push(2);
                            }
                            if operation == 2 {
                                expected.push(3);
                            }
                        }
                        let mut actual = Vec::new();
                        while result.actions != 0 {
                            actual.push((result.actions & 255) as u8);
                            result.actions >>= 8;
                        }
                        assert_eq!(actual, expected);
                        assert_eq!(
                            result.owner,
                            if expected.first() == Some(&1) {
                                owner
                            } else {
                                ptr::null_mut()
                            }
                        );
                        assert_eq!(live, [0x5a; 8]);
                    }
                }
            }
        }
    }
    #[test]
    fn invalid_operation_clears_output_and_null_output_is_refused() {
        let mut token = 0u8;
        let owner = &mut token as *mut u8;
        let mut output = StringOwnershipPlan {
            owner,
            actions: u64::MAX,
        };
        assert_eq!(
            unsafe { swr_v1_string_ownership_plan(3, 0, 1, owner, &mut output) },
            INVALID
        );
        assert!(output.owner.is_null());
        assert_eq!(output.actions, 0);
        assert_eq!(
            unsafe { swr_v1_string_ownership_plan(0, 0, 0, ptr::null_mut(), ptr::null_mut()) },
            INVALID
        );
    }
}
