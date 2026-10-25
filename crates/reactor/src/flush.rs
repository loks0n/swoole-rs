//! Writable-queue and drain orchestration. Native supplies fresh facts and runs
//! exactly one socket/timer/reactor effect after each returned action.
#[repr(C)]
#[derive(Default)]
pub struct FlushState {
    pub phase: u32,
}

/// Writable flags: empty1, close-wait2, send-wait4, timer8. Kind matches frozen
/// DATA0/SENDFILE1/CLOSE2. Actions: done0, send-data1, sendfile2, close3,
/// trigger-close4, delete-timer6, remove-write7, refresh-loop9.
/// # Safety
/// State is initialized to zero, exclusively accessed and live. No socket,
/// Buffer/Chunk pointer or borrow is retained; all native effects run on return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_flush_step(
    state: *mut FlushState,
    flags: u32,
    kind: u32,
    result: i32,
) -> i32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if flags & !15 != 0 || state.phase > 5 {
        return -1;
    }
    loop {
        match state.phase {
            0 if flags & 1 == 0 => {
                state.phase = if kind == 2 { 5 } else { 1 };
                return match kind {
                    1 => 2,
                    2 => 3,
                    _ => 1,
                };
            }
            0 => state.phase = 3,
            1 => {
                if result < 0 {
                    if flags & 2 != 0 {
                        state.phase = 5;
                        return 4;
                    }
                    if flags & 4 != 0 {
                        state.phase = 5;
                        return 0;
                    }
                }
                state.phase = 0;
                return 9;
            }
            3 => {
                state.phase = 4;
                if flags & 8 != 0 {
                    return 6;
                }
            }
            4 => {
                state.phase = 5;
                return if flags & 1 != 0 { 7 } else { 0 };
            }
            5 => return 0,
            _ => return -1,
        }
    }
}

/// Drain flags: empty1, close-wait2, removed4. Actions done0, native-wait1,
/// writable-callback2, refresh-loop3. The writable result is intentionally
/// ignored, matching the original; only wait == SW_ERR(-1) terminates early.
/// # Safety
/// State is zero initialized and exclusively accessed; no native borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_drain_step(
    state: *mut FlushState,
    flags: u32,
    result: i32,
) -> i32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if flags & !7 != 0 || state.phase > 3 {
        return -1;
    }
    match state.phase {
        0 if flags & 1 == 0 => {
            state.phase = 1;
            1
        }
        1 if result != -1 => {
            state.phase = 2;
            2
        }
        2 if flags & 6 == 0 => {
            state.phase = 0;
            3
        }
        _ => {
            state.phase = 3;
            0
        }
    }
}

/// Complete fresh-observation workflow. Actions 10..15 request respectively
/// empty, front kind, close-wait, send-wait, timer, removed. Other actions retain
/// the legacy effect numbers. Input is only the preceding observation/effect's
/// result. Native must return before performing any requested operation.
/// # Safety
/// State is zero-initialized, live and exclusive for this workflow only. No
/// native pointers, borrowed bytes or effects enter Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_flush_workflow(
    state: *mut FlushState,
    observed: i32,
) -> i32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    let (phase, action) = match state.phase {
        0 => (1, 10),
        1 if observed != 0 => (3, 14),
        1 => (2, 11),
        2 => match observed {
            2 => (9, 3),
            1 => (4, 2),
            _ => (4, 1),
        },
        3 if observed != 0 => (7, 6),
        3 | 7 => (8, 10),
        4 if observed < 0 => (5, 12),
        4 => (1, 10),
        5 if observed != 0 => (9, 4),
        5 => (6, 13),
        6 if observed != 0 => (9, 0),
        6 => (1, 10),
        8 => (9, if observed != 0 { 7 } else { 0 }),
        9 => (9, 0),
        _ => return -1,
    };
    state.phase = phase;
    action
}

/// Drain's complete observation ordering. Uses the same request/action numbers
/// as flush, with action1 wait and action2 writable invocation. The invocation
/// result is ignored, matching the pinned original.
/// # Safety
/// Same ownership contract as flush_workflow; use independently initialized state.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_drain_workflow(
    state: *mut FlushState,
    observed: i32,
) -> i32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    let (phase, action) = match state.phase {
        0 => (1, 10),
        1 if observed == 0 => (2, 1),
        1 => (9, 0),
        2 if observed != -1 => (3, 2),
        2 => (9, 0),
        3 => (4, 12),
        4 if observed == 0 => (5, 15),
        4 => (9, 0),
        5 if observed == 0 => (1, 10),
        5 | 9 => (9, 0),
        _ => return -1,
    };
    state.phase = phase;
    action
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(
        workflow: unsafe extern "C" fn(*mut FlushState, i32) -> i32,
        observations: &[i32],
    ) -> Vec<i32> {
        let mut state = FlushState::default();
        observations
            .iter()
            .map(|&fact| unsafe { workflow(&mut state, fact) })
            .collect()
    }
    #[test]
    fn workflow_requests_fresh_empty_after_timer_even_when_timer_absent() {
        assert_eq!(
            trace(swr_v1_reactor_flush_workflow, &[0, 1, 0, 1]),
            [10, 14, 10, 7]
        );
        assert_eq!(
            trace(swr_v1_reactor_flush_workflow, &[0, 1, 1, 0, 0]),
            [10, 14, 6, 10, 0]
        );
    }
    #[test]
    fn workflow_reobserves_after_each_successful_data_effect() {
        assert_eq!(
            trace(
                swr_v1_reactor_flush_workflow,
                &[0, 0, 0, 1, 0, 1, 2, 1, 0, 1]
            ),
            [10, 11, 1, 10, 11, 2, 10, 14, 10, 7]
        );
    }
    #[test]
    fn workflow_drain_ignores_callback_result_then_observes_in_original_order() {
        assert_eq!(
            trace(swr_v1_reactor_drain_workflow, &[0, 0, 0, 7, 0, 0, 1]),
            [10, 1, 2, 12, 15, 10, 0]
        );
    }
    #[test]
    fn workflow_classifier_short_circuits_are_pure_values_only() {
        for result in [-2, -1, 0, 1] {
            for close_wait in [0, 1] {
                for send_wait in [0, 1] {
                    let mut state = FlushState { phase: 4 };
                    let action = unsafe { swr_v1_reactor_flush_workflow(&mut state, result) };
                    if result >= 0 {
                        assert_eq!(action, 10);
                        continue;
                    }
                    assert_eq!(action, 12);
                    let action = unsafe { swr_v1_reactor_flush_workflow(&mut state, close_wait) };
                    if close_wait != 0 {
                        assert_eq!(action, 4);
                        continue;
                    }
                    assert_eq!(action, 13);
                    assert_eq!(
                        unsafe { swr_v1_reactor_flush_workflow(&mut state, send_wait) },
                        if send_wait != 0 { 0 } else { 10 }
                    );
                }
            }
            assert_eq!(
                trace(swr_v1_reactor_drain_workflow, &[0, 0, result]),
                [10, 1, if result == -1 { 0 } else { 2 }]
            );
        }
    }
    #[test]
    fn workflow_invalid_states_fail_without_mutation() {
        let mut state = FlushState { phase: 100 };
        assert_eq!(unsafe { swr_v1_reactor_flush_workflow(&mut state, 0) }, -1);
        assert_eq!(unsafe { swr_v1_reactor_drain_workflow(&mut state, 0) }, -1);
        assert_eq!(state.phase, 100);
    }
    #[test]
    fn actual_result_flags_precede_next_queue_observation() {
        unsafe {
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 0, 0, 0), 1);
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 4, 0, -1), 0);
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 0, 1, 0), 2);
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 6, 0, -1), 4);
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 0, 2, 0), 3);
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 0, 17, 0), 1);
        }
    }
    #[test]
    fn timer_effect_is_followed_by_fresh_queue_facts() {
        unsafe {
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 9, 0, 0), 6);
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 0, 0, 0), 0);
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_flush_step(&mut state, 1, 0, 0), 7);
        }
    }
    #[test]
    fn drain_wait_and_post_callback_stop_order_remains_distinct() {
        unsafe {
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_drain_step(&mut state, 0, 0), 1);
            assert_eq!(swr_v1_reactor_drain_step(&mut state, 0, 0), 2);
            assert_eq!(swr_v1_reactor_drain_step(&mut state, 4, 0), 0);
            let mut state = FlushState::default();
            assert_eq!(swr_v1_reactor_drain_step(&mut state, 0, 0), 1);
            assert_eq!(swr_v1_reactor_drain_step(&mut state, 0, -1), 0);
        }
    }
}
