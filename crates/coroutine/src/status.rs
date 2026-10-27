//! Coupled inline lifecycle status; Native alone owns context/callback effects.
use crate::{Plan, coroutine_transition};

#[repr(C)]
#[derive(Clone, Copy)]
pub struct CoroutineStatus {
    pub state: i32,
    pub code: i32,
}

#[repr(C)]
pub struct CoroutineStatusView {
    pub state: i32,
    pub code: i32,
    pub canceled: u8,
    pub timedout: u8,
    pub suspending: u8,
}

/// # Safety
/// Status is initialized, aligned readable storage with serialized access. No
/// whole Coroutine, Native pointee or borrowed record crosses the return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_status_read(
    status: *const CoroutineStatus,
) -> CoroutineStatusView {
    // SAFETY: per this function's `# Safety` contract, `status` is live, aligned and initialized.
    read(unsafe { &*status })
}

pub(crate) fn read(status: &CoroutineStatus) -> CoroutineStatusView {
    CoroutineStatusView {
        state: status.state,
        code: status.code,
        canceled: u8::from(status.code == -2),
        timedout: u8::from(status.code == -1),
        suspending: u8::from(status.state == 1),
    }
}

/// Complete lifecycle decision/publication. Stage0 decides without mutation;
/// stage1 publishes at the original Native barrier. Cancel admission precedes
/// Native function copy/clear; its commit follows both effects. Op8 publishes
/// timeout before Native resume, and does not extend the frozen copied-fact API.
/// # Safety
/// Status is exclusive live initialized storage, separate from Native effects.
/// The caller preserves the original phase/effect order and fresh observations;
/// no borrow or frame survives return into callbacks, clocks or context switches.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_status_transition(
    status: *mut CoroutineStatus,
    op: u32,
    facts: u32,
    stage: u32,
) -> Plan {
    // SAFETY: per this function's `# Safety` contract, `status` is live, aligned and exclusive.
    transition(unsafe { &mut *status }, op, facts, stage)
}

pub(crate) fn transition(status: &mut CoroutineStatus, op: u32, facts: u32, stage: u32) -> Plan {
    let plan = if op == 8 {
        Plan {
            actions: 0,
            state: -1,
            resume_code: -1,
            error: 0,
        }
    } else {
        coroutine_transition(op, facts, status.code)
    };
    if stage == 1 {
        if plan.state != -1 {
            status.state = plan.state;
        }
        if plan.resume_code != i32::MIN {
            status.code = plan.resume_code;
        }
    }
    plan
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn owned_publication_preserves_admission_and_separate_native_effect_barriers() {
        let mut status = CoroutineStatus { state: 0, code: 0 };
        unsafe {
            let run = swr_v1_coroutine_status_transition(&raw mut status, 0, 0, 0);
            assert_eq!((status.state, status.code), (0, 0));
            // Native current/origin and clock effects finish before stage1.
            assert_eq!(
                swr_v1_coroutine_status_transition(&raw mut status, 0, 0, 1),
                run
            );
            assert_eq!((status.state, status.code), (2, 0));
            for op in 0..8 {
                for facts in 0..64 {
                    for code in [-2, -1, 0] {
                        status = CoroutineStatus { state: 2, code };
                        let expected = coroutine_transition(op, facts, code);
                        let decided =
                            swr_v1_coroutine_status_transition(&raw mut status, op, facts, 0);
                        assert_eq!(decided, expected);
                        assert_eq!((status.state, status.code), (2, code));
                        let applied =
                            swr_v1_coroutine_status_transition(&raw mut status, op, facts, 1);
                        assert_eq!(applied, expected);
                        assert_eq!(
                            status.state,
                            if expected.state == -1 {
                                2
                            } else {
                                expected.state
                            }
                        );
                        assert_eq!(
                            status.code,
                            if expected.resume_code == i32::MIN {
                                code
                            } else {
                                expected.resume_code
                            }
                        );
                    }
                }
            }
            status = CoroutineStatus { state: 1, code: 0 };
            let admitted =
                swr_v1_coroutine_status_transition(&raw mut status, 3, crate::CANCELABLE, 0);
            assert_eq!(admitted.resume_code, -2);
            assert_eq!(status.code, 0); // Native copy/clear can still occur.
            swr_v1_coroutine_status_transition(&raw mut status, 3, crate::CANCELABLE, 1);
            let view = swr_v1_coroutine_status_read(&raw const status);
            assert_eq!(
                (
                    view.state,
                    view.code,
                    view.canceled,
                    view.timedout,
                    view.suspending
                ),
                (1, -2, 1, 0, 1)
            );
            swr_v1_coroutine_status_transition(&raw mut status, 8, 0, 1);
            let view = swr_v1_coroutine_status_read(&raw const status);
            assert_eq!((view.code, view.canceled, view.timedout), (-1, 0, 1));
            assert_eq!(coroutine_transition(8, 0, 0).error, -4); // Old API unchanged.
        }
    }
}
