//! Writable-queue and drain orchestration. Native supplies fresh facts and runs
//! exactly one socket/timer/reactor effect after each returned action.
#[repr(C)]
#[derive(Default)]
pub struct FlushState {
    pub phase: u32,
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
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
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
            .map(|&fact| unsafe { workflow(&raw mut state, fact) })
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
}
