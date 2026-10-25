//! Sole typed swap-callback identities and whole lifecycle dispatch metadata.
//! Native invokes the returned function only after this Rust frame has returned.
use crate::{CoroutineIdentity, CoroutineStatus, Plan};
use std::ffi::c_void;
use std::ptr;

pub type CoroutineSwapFunction = unsafe extern "C" fn(*mut c_void);

#[repr(C)]
pub struct CoroutineSwapCallback {
    pub function: Option<CoroutineSwapFunction>,
}

#[repr(C)]
pub struct CoroutineDispatch {
    pub plan: Plan,
    pub function: Option<CoroutineSwapFunction>,
    pub task: *mut c_void,
}

/// # Safety
/// Cell is exclusive writable storage in its original Native TLS/global scope.
/// Function is a null or valid original typed callback. It is never invoked here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_swap_publish(
    cell: *mut CoroutineSwapCallback,
    function: Option<CoroutineSwapFunction>,
) {
    unsafe { cell.write(CoroutineSwapCallback { function }) };
}

/// Complete yield/resume/close admission, status publication and descriptor.
/// Resume bailout returns before observing callback/task cells. Task is observed
/// only if the callback exists. Native alone invokes a descriptor, then freshly
/// routes current/origin and performs its original clocks/context/erase effects.
/// # Safety
/// Status is exclusive initialized storage. Callback/task are separate live
/// initialized readable cells, serialized as the original Native identities.
/// Rejected/short-circuited cells are not accessed. No Native pointee is read,
/// no function is called and no Rust reference/frame survives return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_dispatch(
    status: *mut CoroutineStatus,
    operation: u32,
    callback: *const CoroutineSwapCallback,
    task: *const CoroutineIdentity,
    bailout: u8,
) -> CoroutineDispatch {
    if !matches!(operation, 1 | 2 | 4) {
        return CoroutineDispatch {
            plan: Plan {
                actions: 0,
                state: -1,
                resume_code: i32::MIN,
                error: -4,
            },
            function: None,
            task: ptr::null_mut(),
        };
    }
    let function = if operation == 1 && bailout != 0 {
        None
    } else {
        unsafe { (*callback).function }
    };
    let token = if function.is_some() {
        unsafe { (*task).token }
    } else {
        ptr::null_mut()
    };
    let facts = (u32::from(bailout != 0) * crate::BAILOUT)
        | (u32::from(function.is_some()) * crate::CALLBACK)
        | (u32::from(!token.is_null()) * crate::TASK);
    let plan = crate::status::transition(unsafe { &mut *status }, operation, facts, 1);
    let admitted = plan.actions & crate::CALL != 0;
    CoroutineDispatch {
        plan,
        function: if admitted { function } else { None },
        task: if admitted { token } else { ptr::null_mut() },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::MaybeUninit;

    unsafe extern "C" fn identity_only(_: *mut c_void) {}

    #[test]
    fn typed_descriptors_match_native_admission_without_invoking_callbacks() {
        let mut cell = MaybeUninit::<CoroutineSwapCallback>::uninit();
        let mut byte = 1_u8;
        let token = ptr::from_mut(&mut byte).cast();
        unsafe {
            for op in [1, 2, 4] {
                for present in [false, true] {
                    swr_v1_coroutine_swap_publish(
                        cell.as_mut_ptr(),
                        present.then_some(identity_only),
                    );
                    for task in [ptr::null_mut(), token] {
                        for bailout in [0, 1] {
                            let mut status = CoroutineStatus { state: 0, code: -2 };
                            let task = CoroutineIdentity { token: task };
                            let result = swr_v1_coroutine_dispatch(
                                &raw mut status,
                                op,
                                cell.as_ptr(),
                                &task,
                                bailout,
                            );
                            let proceed = op != 1 || bailout == 0;
                            let admitted = proceed && present && !task.token.is_null();
                            assert_eq!(result.function.is_some(), admitted);
                            assert_eq!(
                                result.task,
                                if admitted {
                                    task.token
                                } else {
                                    ptr::null_mut()
                                }
                            );
                            if let Some(function) = result.function {
                                assert!(std::ptr::fn_addr_eq(
                                    function,
                                    identity_only as CoroutineSwapFunction
                                ));
                            }
                            assert_eq!(
                                status.state,
                                if !proceed {
                                    0
                                } else if op == 2 {
                                    1
                                } else if op == 4 {
                                    3
                                } else {
                                    2
                                }
                            );
                            assert_eq!(status.code, if op == 2 { 0 } else { -2 });
                        }
                    }
                }
            }
            let mut status = CoroutineStatus { state: 0, code: 0 };
            // Bailout and absent callback must not observe rejected cells.
            swr_v1_coroutine_dispatch(&raw mut status, 1, ptr::null(), ptr::null(), 1);
            swr_v1_coroutine_swap_publish(cell.as_mut_ptr(), None);
            swr_v1_coroutine_dispatch(&raw mut status, 2, cell.as_ptr(), ptr::null(), 0);
        }
        assert_eq!(byte, 1);
    }
}
