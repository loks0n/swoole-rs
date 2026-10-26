//! Whole kqueue signal routing, with Native signal and handler custody.
//! Requests preserve short-circuit reads; effects run only after Rust returns.
#[repr(C)]
#[derive(Default)]
pub struct ReactorSignalState {
    pub phase: u32,
}

/// Actions0 done,1 invoke,2 warn; observations10 activated,11 handler present,
///12 handler differs from SIG_IGN. No Signal/function pointer enters Rust.
/// # Safety
/// State is a live exclusive initialized POD, independent of Native effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_signal_workflow(
    state: *mut ReactorSignalState,
    observed: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    let (phase, action) = match state.phase {
        0 => (1, 10),
        1 if observed != 0 => (2, 11),
        1 => (4, 0),
        2 if observed != 0 => (3, 12),
        2 => (4, 2),
        3 => (4, i32::from(observed != 0)),
        4 => (4, 0),
        _ => return -1,
    };
    state.phase = phase;
    action
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_short_circuit_traces_use_only_requested_scalar_observations() {
        assert_eq!(std::mem::size_of::<ReactorSignalState>(), 4);
        for activated in [0, 1] {
            for present in [0, 1] {
                for callable in [0, 1] {
                    let mut state = ReactorSignalState::default();
                    let mut trace = vec![];
                    let mut observed = 0;
                    loop {
                        let action =
                            unsafe { swr_v1_reactor_signal_workflow(&mut state, observed) };
                        trace.push(action);
                        observed = match action {
                            10 => activated,
                            11 => present,
                            12 => callable,
                            0..=2 => break,
                            _ => panic!("invalid positive source trace"),
                        };
                    }
                    // Independent original nested policy, with no Signal or
                    // Native handler invocation/log/error execution.
                    let expected = if activated == 0 {
                        vec![10, 0]
                    } else if present == 0 {
                        vec![10, 11, 2]
                    } else {
                        vec![10, 11, 12, callable]
                    };
                    assert_eq!(trace, expected);
                    assert_eq!(state.phase, 4);
                    assert_eq!(unsafe { swr_v1_reactor_signal_workflow(&mut state, 1) }, 0);
                }
            }
        }
    }
}
