//! Whole per-record observation and result sequencing. Native retains actual
//! record/Socket reads, handler invocations, logging and one-shot deletion.
use crate::{ReadyState, swr_v1_reactor_ready_step};

#[repr(C)]
#[derive(Default)]
pub struct ReadyWorkflow {
    ready: ReadyState,
    phase: u32,
    mask: u32,
    once: u32,
    callback: u32,
}

#[expect(
    clippy::cast_sign_loss,
    reason = "native int/uint32_t callback and mask fields"
)]
fn resolve(state: &mut ReadyWorkflow, backend: u32, removed: u32, known: u32) -> i32 {
    // SAFETY: `state.ready` is a live, exclusive local field; the step takes it for this call only.
    let action = unsafe {
        swr_v1_reactor_ready_step(
            &mut state.ready,
            backend,
            state.mask,
            removed,
            known,
            state.once,
        )
    };
    match action {
        1..=3 => {
            state.callback = action as u32;
            state.phase = 4;
        }
        5 => {
            state.phase = 3;
            return 12;
        }
        _ => state.phase = 9,
    }
    action
}

/// Backend0 poll/epoll,1 kqueue. Effects1read/2write/3error/4once-remove,
/// 6read-warning/7write-warning/8error-warning. Requests10mask/11removed/12once.
/// Input is the immediately preceding fact or Native handler result; other
/// effect results are ignored. Mask is refreshed even after the ONCE read,
/// preserving the existing selected batch-observation contract.
/// # Safety
/// State is independently zero-initialized/live/exclusive. Native executes all
/// observations/effects after return. No Native token/pointer/borrow is retained.
#[unsafe(no_mangle)]
#[expect(
    clippy::cast_possible_wrap,
    clippy::cast_sign_loss,
    reason = "native int/uint32_t callback and mask fields"
)]
pub unsafe extern "C" fn swr_v1_reactor_ready_workflow(
    state: *mut ReadyWorkflow,
    backend: u32,
    observed: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if backend > 1 {
        return -1;
    }
    loop {
        match state.phase {
            0 => {
                state.phase = 1;
                return 10;
            }
            1 => {
                if observed < 0 || observed & !7 != 0 {
                    return -1;
                }
                state.mask = observed as u32;
                state.phase = 2;
                return 11;
            }
            2 => return resolve(state, backend, u32::from(observed != 0), 0),
            3 => {
                state.once = u32::from(observed != 0);
                state.phase = 5;
                return 10;
            }
            4 => {
                state.phase = 0;
                if observed < 0 {
                    return state.callback as i32 + 5;
                }
            }
            5 => {
                if observed < 0 || observed & !7 != 0 {
                    return -1;
                }
                state.mask = observed as u32;
                return resolve(state, backend, 0, 1);
            }
            9 => return 0,
            _ => return -1,
        }
    }
}

#[cfg(test)]
#[expect(
    clippy::cast_possible_wrap,
    reason = "tests drive the native integer interfaces with literal and loop values"
)]
mod tests {
    use super::*;
    fn trace(backend: u32, facts: &[i32]) -> Vec<i32> {
        let mut state = ReadyWorkflow::default();
        facts
            .iter()
            .map(|&fact| unsafe { swr_v1_reactor_ready_workflow(&mut state, backend, fact) })
            .collect()
    }
    #[test]
    fn actual_ready_policy_requests_mask_removed_and_once_in_order() {
        for backend in 0..2 {
            assert_eq!(
                trace(backend, &[0, 1, 0, 0, 1, 0, 1, 1]),
                [10, 11, 1, 10, 11, 12, 10, 4]
            );
            assert_eq!(
                trace(backend, &[0, 1, 0, 0, 1, 0, 0, 1]),
                [10, 11, 1, 10, 11, 12, 10, 0]
            );
        }
    }
    #[test]
    fn ready_workflow_refreshes_record_before_write_after_read() {
        assert_eq!(
            trace(0, &[0, 3, 0, 0, 3, 0, 0, 3, 0, 1, 3]),
            [10, 11, 1, 10, 11, 2, 10, 11, 12, 10, 4]
        );
        assert_eq!(
            trace(0, &[0, 1, 0, 0, 0, 0, 0, 0]),
            [10, 11, 1, 10, 11, 12, 10, 0]
        );
    }
    #[test]
    fn warning_selection_uses_only_rust_scalar_results() {
        for (mask, callback) in [(1, 1), (2, 2), (4, 3)] {
            assert_eq!(
                trace(0, &[0, mask, 0, -1, 0]),
                [10, 11, callback, callback + 5, 10]
            );
        }
    }
    #[test]
    fn observation_trace_matches_frozen_step_driver_for_512_pure_value_cases() {
        for backend in 0..2 {
            for first in 0..8 {
                for later in 0..8 {
                    for removed in 0..2 {
                        for once in 0..2 {
                            let mut old = ReadyState::default();
                            let mut known = 0;
                            let mut count = 0;
                            let mut expected = Vec::new();
                            loop {
                                expected.push(10);
                                let mask = if count == 0 { first } else { later };
                                count += 1;
                                if known == 0 {
                                    expected.push(11);
                                }
                                let action = unsafe {
                                    swr_v1_reactor_ready_step(
                                        &mut old,
                                        backend,
                                        mask,
                                        if known == 0 { removed } else { 0 },
                                        known,
                                        once,
                                    )
                                };
                                if action <= 0 {
                                    break;
                                }
                                if action == 5 {
                                    expected.push(12);
                                    known = 1;
                                    continue;
                                }
                                expected.push(action);
                                known = 0;
                                if action == 4 {
                                    break;
                                }
                            }
                            let mut state = ReadyWorkflow::default();
                            let mut observed = 0;
                            let mut actual = Vec::new();
                            let mut count = 0;
                            loop {
                                assert!(actual.len() < 64);
                                let action = unsafe {
                                    swr_v1_reactor_ready_workflow(&mut state, backend, observed)
                                };
                                if action <= 0 {
                                    break;
                                }
                                actual.push(action);
                                observed = match action {
                                    10 => {
                                        let value = if count == 0 { first } else { later };
                                        count += 1;
                                        value as i32
                                    }
                                    11 => removed as i32,
                                    12 => once as i32,
                                    _ => 0,
                                };
                                if action == 4 {
                                    break;
                                }
                            }
                            assert_eq!(
                                actual, expected,
                                "backend{backend} masks{first}/{later} removed{removed} once{once}"
                            );
                        }
                    }
                }
            }
        }
    }
    #[test]
    fn layout_and_invalid_facts_remain_explicit() {
        assert_eq!(std::mem::size_of::<ReadyWorkflow>(), 20);
        assert_eq!(trace(0, &[0, 8]), [10, -1]);
        assert_eq!(trace(2, &[0]), [-1]);
    }
}
