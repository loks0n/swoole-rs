//! Complete ordinary output observation sequencing; Native owns every task,
//! chunk, byte pointer, allocator and syscall effect outside Rust frames.
use crate::{
    ReactorOutputAction, swr_v1_reactor_output_data, swr_v1_reactor_output_file,
    swr_v1_reactor_output_request,
};

#[repr(C)]
#[derive(Default)]
pub struct OutputWorkflow {
    phase: u32,
    pending: u32,
    requested: u32,
    flags: u32,
    length: u32,
    offset: u32,
    corked: i32,
    error: i32,
    begin: i64,
    end: i64,
    result: i64,
    previous_action: i32,
    validation: i32,
}
fn observation(state: &mut OutputWorkflow, action: u32) -> ReactorOutputAction {
    state.pending = action;
    ReactorOutputAction {
        phase: state.phase,
        action: action as i32,
        value: 0,
    }
}
fn prepare(state: &mut OutputWorkflow, operation: u32) -> Option<ReactorOutputAction> {
    let action = match (operation, state.phase) {
        (0, 0) => 16,
        (0, 3) => 17,
        (1, 0 | 9) => 18,
        (1, 5 | 10) => 19,
        (1, 11) => 21,
        (2, 3) => 22,
        _ => return None,
    };
    Some(observation(state, action))
}
fn resolve(state: &mut OutputWorkflow, operation: u32, cork_min: i64) -> ReactorOutputAction {
    loop {
        let reply = match operation {
            0 => swr_v1_reactor_output_data(
                state.phase,
                state.requested,
                state.length,
                state.offset,
                state.result as isize,
                state.error,
            ),
            1 => swr_v1_reactor_output_file(
                state.phase,
                state.corked,
                state.begin,
                state.end,
                cork_min,
                state.result as isize,
                state.error,
                state.flags,
            ),
            _ => swr_v1_reactor_output_request(state.phase, state.validation, state.flags),
        };
        state.phase = reply.phase;
        // These frozen actions only requested another planning pass. Native
        // previously did no effect, so continue until an actual read/effect.
        if matches!((operation, reply.action), (0, 7) | (1, 11) | (2, 8)) {
            if let Some(request) = prepare(state, operation) {
                return request;
            }
            continue;
        }
        if operation == 0 && reply.action == 1 {
            state.requested = reply.value as u32;
        }
        state.previous_action = reply.action;
        state.pending = 255;
        return reply;
    }
}
/// Operation0 DATA,1 queued file,2 enqueue request. Existing effect numbers are
/// retained. Requests16length/17offset/18corked/19begin/20end/21timer/22buffer.
/// `observed` is only the preceding fact/effect result, with original C integer
/// conversions; `cork_min` is the actual Native configuration constant.
/// # Safety
/// State is independently zero-initialized/live/exclusive for one operation.
/// No Native pointer, object or callback is passed/stored. Native performs each
/// returned observation/effect after return; all original input domains apply.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_output_workflow(
    state: *mut OutputWorkflow,
    operation: u32,
    observed: i64,
    cork_min: i64,
) -> ReactorOutputAction {
    let invalid = || ReactorOutputAction {
        phase: 0,
        action: -1,
        value: 0,
    };
    let Some(state) = (unsafe { state.as_mut() }) else {
        return invalid();
    };
    if operation > 2 {
        return invalid();
    }
    match state.pending {
        0 => {}
        255 => match (operation, state.previous_action) {
            (0, 1) | (1, 3) => state.result = observed,
            (0, 3) | (1, 4) => state.error = observed as i32,
            (1, 1) => state.flags = if observed != 0 { 2 } else { 0 },
            (2, 2) => state.validation = observed as i32,
            _ => {}
        },
        16 => {
            state.length = observed as u32;
            return observation(state, 17);
        }
        17 => {
            state.offset = observed as u32;
            return resolve(state, operation, cork_min);
        }
        18 => {
            state.corked = observed as i32;
            return resolve(state, operation, cork_min);
        }
        19 => {
            state.begin = observed;
            return observation(state, 20);
        }
        20 => {
            state.end = observed;
            return resolve(state, operation, cork_min);
        }
        21 => {
            state.flags = (state.flags & !1) | u32::from(observed != 0);
            return resolve(state, operation, cork_min);
        }
        22 => {
            state.flags = u32::from(observed != 0);
            return resolve(state, operation, cork_min);
        }
        _ => return invalid(),
    }
    if let Some(request) = prepare(state, operation) {
        return request;
    }
    resolve(state, operation, cork_min)
}

/// Complete file-parameter observation/publication workflow. Effect actions
/// match frozen output_parameters; request23ready/24stat-size/25published-end.
/// `begin`/`length` are original Native arguments, not borrowed object fields.
/// # Safety
/// Independently zero-initialized live/exclusive state for this workflow only.
/// Native filename/stat/end storage, syscalls, diagnostics and effects stay
/// outside Rust. The original defined signed arithmetic domain is preserved.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_output_parameters_workflow(
    state: *mut OutputWorkflow,
    begin: i64,
    length: usize,
    observed: i64,
) -> ReactorOutputAction {
    let invalid = || ReactorOutputAction {
        phase: 0,
        action: -1,
        value: 0,
    };
    let Some(state) = (unsafe { state.as_mut() }) else {
        return invalid();
    };
    match state.pending {
        0 => return observation(state, 23),
        23 => state.validation = observed as i32,
        24 => {
            state.result = observed;
            if state.phase == 3 {
                return observation(state, 25);
            }
        }
        25 => state.end = observed,
        255 if state.previous_action == 1 => state.validation = observed as i32,
        255 if state.previous_action == 5 => return observation(state, 24),
        _ => return invalid(),
    }
    let reply = crate::swr_v1_reactor_output_parameters(
        state.phase,
        state.validation,
        state.result,
        begin,
        length,
        state.end,
    );
    state.phase = reply.phase;
    if reply.action == 7 {
        return observation(state, 24);
    }
    state.pending = 255;
    state.previous_action = reply.action;
    reply
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(operation: u32, facts: &[i64]) -> Vec<(i32, i64)> {
        let mut state = OutputWorkflow::default();
        facts
            .iter()
            .map(|&value| {
                let reply =
                    unsafe { swr_v1_reactor_output_workflow(&mut state, operation, value, 8) };
                (reply.action, reply.value)
            })
            .collect()
    }
    #[test]
    fn parameters_reobserve_size_then_published_end_after_native_publication() {
        for begin in 1..5 {
            for length in 0..7 {
                let end = if length == 0 {
                    31
                } else {
                    begin + length as i64
                };
                let mut state = OutputWorkflow::default();
                let actual: Vec<_> = [0, 1, 1, 31, 0, 31, end]
                    .into_iter()
                    .map(|observed| {
                        let reply = unsafe {
                            swr_v1_reactor_output_parameters_workflow(
                                &mut state, begin, length, observed,
                            )
                        };
                        (reply.action, reply.value)
                    })
                    .collect();
                assert_eq!(
                    actual,
                    [(23, 0), (1, 0), (24, 0), (5, end), (24, 0), (25, 0), (0, 0)]
                );
            }
        }
    }
    #[test]
    fn data_fresh_offset_follows_partial_success_and_full_send_pops() {
        assert_eq!(trace(0, &[0, 9, 2, 7]), [(16, 0), (17, 0), (1, 7), (2, 0)]);
        assert_eq!(
            trace(0, &[0, 9, 2, 3, 2]),
            [(16, 0), (17, 0), (1, 7), (17, 0), (9, 5)]
        );
    }
    #[test]
    fn file_cork_range_timer_and_completion_facts_are_requested_in_order() {
        assert_eq!(
            trace(1, &[0, 0, 2, 30, 1, 0, 5, 1, 0, 7]),
            [
                (18, 0),
                (19, 0),
                (20, 0),
                (1, 0),
                (2, 1),
                (3, 0),
                (21, 0),
                (8, 0),
                (19, 0),
                (20, 0)
            ]
        );
        assert_eq!(
            trace(1, &[0, -1, 4, 0, 4, 4, -1]),
            [(18, 0), (3, 0), (21, 0), (19, 0), (20, 0), (18, 0), (10, 0)]
        );
    }
    #[test]
    fn request_validation_precedes_buffer_observation_without_native_allocation() {
        assert_eq!(
            trace(2, &[0, 0, 1, 0, 0, 0, 0, 0]),
            [
                (1, 0),
                (2, 0),
                (22, 0),
                (3, 0),
                (4, 0),
                (5, 0),
                (6, 0),
                (0, 0)
            ]
        );
        assert_eq!(
            trace(2, &[0, 0, 1, 1, 0, 0, 0]),
            [(1, 0), (2, 0), (22, 0), (4, 0), (5, 0), (6, 0), (0, 0)]
        );
    }
    #[test]
    fn state_layout_and_invalid_operation_are_explicit() {
        assert_eq!(std::mem::size_of::<OutputWorkflow>(), 64);
        let mut state = OutputWorkflow::default();
        assert_eq!(
            unsafe { swr_v1_reactor_output_workflow(&mut state, 3, 0, 8) }.action,
            -1
        );
    }
}
