//! Backend outer wait sequencing. Native owns kernel waits, callbacks and error
//! observation. No clock acquisition, timer manager or second executor exists.
#[repr(C)]
#[derive(Default)]
pub struct WaitState {
    pub phase: u32,
}

/// Backend0poll/1epoll/2kqueue. Flags running1/once2/interrupted4/uring-handler8.
/// Actions done0,before1,begin2,kernel-wait3,catch4,end-timeout5,dispatch6,
/// warning7,uring-interrupt8,end-normal9; -2 preserves epoll/kqueue error return.
/// # Safety
/// State is zero initialized/live/exclusive. All Native effects run after return;
/// facts after an effect are fresh and no pointer/borrow/callback is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_wait_step(
    state: *mut WaitState,
    backend: u32,
    flags: u32,
    result: i32,
    caught: u32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if backend > 2 || flags & !15 != 0 {
        return -1;
    }
    loop {
        match state.phase {
            0 => {
                state.phase = 1;
                return 1;
            }
            1 if flags & 1 != 0 => {
                state.phase = 2;
                return 2;
            }
            1 => {
                state.phase = 8;
                return 0;
            }
            2 => {
                state.phase = 3;
                return 3;
            }
            3 if result < 0 => {
                state.phase = 4;
                return 4;
            }
            3 if result == 0 => {
                state.phase = 6;
                return 5;
            }
            3 => {
                state.phase = 5;
                return 6;
            }
            4 if caught == 0 => {
                state.phase = 7;
                return 7;
            }
            4 if backend == 1 && flags & 12 == 12 => {
                state.phase = 5;
                return 8;
            }
            4 | 5 => {
                state.phase = 6;
                return 9;
            }
            6 if flags & 2 != 0 => {
                state.phase = 8;
                return 0;
            }
            6 => state.phase = 1,
            7 => {
                state.phase = 8;
                return if backend == 0 { 0 } else { -2 };
            }
            8 => return 0,
            _ => return -1,
        }
    }
}

/// Complete outer wait observation workflow. Same effects0..9/-2 as wait_step;
/// request10 reads running,11 compares Native errno with EINTR,12 reads uring
/// handler presence,13 reads once. Native supplies0 for11 without IOURING.
/// Each reply consumes only the immediately preceding fact/effect result.
/// # Safety
/// State is independently zero initialized/live/exclusive for this workflow.
/// Native effects and observations occur after return; no object is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_wait_workflow(
    state: *mut WaitState,
    backend: u32,
    observed: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if backend > 2 {
        return -1;
    }
    let (phase, action) = match state.phase {
        0 => (1, 1),
        1 => (2, 10),
        2 if observed != 0 => (3, 2),
        2 => (14, 0),
        3 => (4, 3),
        4 if observed < 0 => (5, 4),
        4 if observed == 0 => (9, 5),
        4 => (8, 6),
        5 if observed == 0 => (12, 7),
        5 if backend == 1 => (6, 11),
        5 => (9, 9),
        6 if observed != 0 => (7, 12),
        6 => (9, 9),
        7 if observed != 0 => (8, 8),
        7 | 8 => (9, 9),
        9 => (10, 13),
        10 if observed == 0 => (2, 10),
        10 | 14 => (14, 0),
        12 => (14, if backend == 0 { 0 } else { -2 }),
        _ => return -1,
    };
    state.phase = phase;
    action
}

#[repr(C)]
pub struct KqueueTimeout {
    pub seconds: i64,
    pub nanoseconds: i64,
    pub finite: u32,
}

/// Preserve kqueue's positive-timeout priority over deferred work, unlike the
/// poll/epoll Native get_timeout_msec helper. Native constructs its timespec.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_kqueue_timeout(milliseconds: i32, deferred: u32) -> KqueueTimeout {
    if milliseconds > 0 {
        KqueueTimeout {
            seconds: i64::from(milliseconds / 1000),
            nanoseconds: i64::from(milliseconds % 1000) * 1_000_000,
            finite: 1,
        }
    } else {
        KqueueTimeout {
            seconds: 0,
            nanoseconds: 0,
            finite: u32::from(deferred != 0),
        }
    }
}

/// Like the frozen readiness ABI, but request action5 when the ONCE fact is
/// actually needed. Trial decisions retain no Native borrow and commit only
/// after all needed facts exist. Native must stop the record after action4.
/// # Safety
/// Same state contract as swr_v1_reactor_ready. Once is read by Native only after
/// action5; never before a read/write/error callback whose result precedes it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_ready_step(
    state: *mut super::ReadyState,
    backend: u32,
    mask: u32,
    removed: u32,
    once_known: u32,
    once: u32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    let mut trial = super::ReadyState { phase: state.phase };
    // SAFETY: `trial` is a live local; the step reads and writes it for this call only.
    let action = unsafe {
        super::swr_v1_reactor_ready(
            &mut trial,
            backend,
            mask,
            removed,
            if once_known != 0 { once } else { 1 },
        )
    };
    if action == 4 && once_known == 0 {
        return 5;
    }
    state.phase = trial.phase;
    action
}

#[cfg(test)]
mod tests {
    use super::*;
    fn workflow_trace(backend: u32, facts: &[i32]) -> Vec<i32> {
        let mut state = WaitState::default();
        facts
            .iter()
            .map(|&value| unsafe { swr_v1_reactor_wait_workflow(&mut state, backend, value) })
            .collect()
    }
    #[test]
    fn wait_workflow_positive_requests_each_fact_after_its_effect() {
        for backend in 0..3 {
            assert_eq!(
                workflow_trace(backend, &[0, 0, 1, 0, 2, 0, 0, 1]),
                [1, 10, 2, 3, 6, 9, 13, 0]
            );
            assert_eq!(
                workflow_trace(backend, &[0, 0, 1, 0, 0, 0, 0, 0]),
                [1, 10, 2, 3, 5, 13, 10, 0]
            );
            assert_eq!(workflow_trace(backend, &[0, 0, 0]), [1, 10, 0]);
        }
    }
    #[test]
    fn wait_workflow_pure_catch_and_uring_classification_only() {
        for backend in 0..3 {
            assert_eq!(
                workflow_trace(backend, &[0, 0, 1, 0, -1, 0, 0]),
                [1, 10, 2, 3, 4, 7, if backend == 0 { 0 } else { -2 }]
            );
            if backend != 1 {
                assert_eq!(
                    workflow_trace(backend, &[0, 0, 1, 0, -1, 1, 0, 1]),
                    [1, 10, 2, 3, 4, 9, 13, 0]
                );
            }
        }
        assert_eq!(
            workflow_trace(1, &[0, 0, 1, 0, -1, 1, 0, 0, 1]),
            [1, 10, 2, 3, 4, 11, 9, 13, 0]
        );
        assert_eq!(
            workflow_trace(1, &[0, 0, 1, 0, -1, 1, 1, 0, 0, 1]),
            [1, 10, 2, 3, 4, 11, 12, 9, 13, 0]
        );
        assert_eq!(
            workflow_trace(1, &[0, 0, 1, 0, -1, 1, 1, 1, 0, 0, 1]),
            [1, 10, 2, 3, 4, 11, 12, 8, 9, 13, 0]
        );
    }
    #[test]
    fn wait_positive_preserves_begin_wait_end_once_and_timeout_order() {
        unsafe {
            for backend in 0..3 {
                for result in [0, 1] {
                    let mut state = WaitState::default();
                    for (flags, outcome, expected) in [
                        (0, 0, 1),
                        (1, 0, 2),
                        (0, 0, 3),
                        (0, result, if result == 0 { 5 } else { 6 }),
                    ] {
                        assert_eq!(
                            swr_v1_reactor_wait_step(&mut state, backend, flags, outcome, 0),
                            expected
                        );
                    }
                    if result > 0 {
                        assert_eq!(swr_v1_reactor_wait_step(&mut state, backend, 0, 0, 0), 9);
                    }
                    assert_eq!(swr_v1_reactor_wait_step(&mut state, backend, 2, 0, 0), 0);
                }
            }
        }
        for milliseconds in [1, 999, 1000, 1001, i32::MAX] {
            let plan = swr_v1_reactor_kqueue_timeout(milliseconds, 1);
            assert_eq!(plan.seconds, i64::from(milliseconds / 1000));
            assert_eq!(plan.nanoseconds, i64::from(milliseconds % 1000) * 1_000_000);
            assert_eq!(plan.finite, 1);
        }
        assert_eq!(swr_v1_reactor_kqueue_timeout(0, 1).finite, 1);
    }
    #[test]
    fn wait_positive_once_fact_is_requested_after_callbacks_only() {
        unsafe {
            for backend in 0..2 {
                let mut state = super::super::ReadyState::default();
                assert_eq!(
                    swr_v1_reactor_ready_step(&mut state, backend, 1, 0, 0, 0),
                    1
                );
                assert_eq!(
                    swr_v1_reactor_ready_step(&mut state, backend, 1, 0, 0, 0),
                    5
                );
                assert_eq!(
                    swr_v1_reactor_ready_step(&mut state, backend, 1, 0, 1, 1),
                    4
                );
            }
        }
    }
}
