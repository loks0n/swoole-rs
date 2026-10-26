//! Whole write preparation and fresh observation order around the frozen write
//! progression. Native retains Buffer/Socket pointers, syscalls, allocation,
//! errno acquisition and callbacks; only scalar facts cross the boundary.
use crate::{ReadyState, swr_v1_reactor_write};

#[repr(C)]
#[derive(Default)]
pub struct WriteWorkflow {
    pub phase: u32,
    pub policy: ReadyState,
}
#[repr(C)]
#[derive(Default)]
pub struct WriteFacts {
    pub buffered: usize,
    pub sent: isize,
    pub capacity: u32,
    pub flags: u32,
    pub nonblock: u32,
    pub wait: u32,
    pub interrupted: u32,
}
/// Existing write actions0..9 are unchanged. Additional Native actions:
///10observe buffer size,11set default size,12observe nonblock,13set nonblock,
///14observe admission/overflow capacity,15observe captured Buffer emptiness,16observe TLS-send,
///17observe captured Buffer length,18observe fresh output pointer presence,
///19observe writable interest,20observe errno==EINTR. Fresh facts are supplied
///after each requested effect, without reobserving unrelated Native state.
/// # Safety
/// Both PODs are zero-initialized, aligned/live/exclusive and disjoint. Native
/// retains no Rust borrow/frame over effects and stops on terminal write actions.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_write_workflow(
    state: *mut WriteWorkflow,
    length: usize,
    facts: *mut WriteFacts,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let state = unsafe { state.as_mut() };
    // SAFETY: `facts` is null or live, aligned and exclusively lent for this call.
    let facts = unsafe { facts.as_mut() };
    let (Some(state), Some(facts)) = (state, facts) else {
        return -1;
    };
    loop {
        match state.phase {
            0 => {
                state.phase = 1;
                return 10;
            }
            1 => {
                state.phase = 2;
                if facts.capacity == 0 {
                    return 11;
                }
            }
            2 => {
                state.phase = 3;
                return 12;
            }
            3 => {
                state.phase = 4;
                if facts.nonblock == 0 {
                    return 13;
                }
            }
            4 => {
                state.phase = 5;
                return 14;
            }
            5 => {
                facts.flags = 0;
                facts.buffered = 0;
                state.phase = 8;
                if state.policy.phase == 0 && length as u32 <= facts.capacity {
                    state.phase = 6;
                    return 15;
                }
            }
            6 => {
                state.phase = 8;
                if facts.flags & 1 != 0 {
                    return 16;
                }
                state.phase = 7;
                return 17;
            }
            7 => {
                state.phase = 8;
                return 14;
            }
            8 => {
                state.phase = 10;
                let allocation_facts = (state.policy.phase == 0 && facts.flags & 3 == 3)
                    || (state.policy.phase == 2 && facts.sent > 0 && facts.sent != length as isize)
                    || (state.policy.phase == 3 && facts.wait != 0)
                    || state.policy.phase == 4;
                if allocation_facts {
                    state.phase = 9;
                    return 18;
                }
            }
            9 => {
                state.phase = 10;
                if facts.flags & 4 != 0 {
                    return 19;
                }
            }
            10 => {
                state.phase = 11;
                if state.policy.phase == 5 {
                    return 19;
                }
            }
            11 => {
                state.phase = 12;
                facts.interrupted = 0;
                if state.policy.phase == 3 && facts.wait == 0 {
                    return 20;
                }
            }
            12 => {
                state.phase = 5;
                // SAFETY: `state.policy` is a live, exclusive field of the caller's state.
                return unsafe {
                    swr_v1_reactor_write(
                        &mut state.policy,
                        length,
                        facts.buffered,
                        facts.capacity,
                        facts.flags,
                        facts.sent,
                        facts.wait,
                        facts.interrupted,
                    )
                };
            }
            _ => return -1,
        }
    }
}

/// Target layout facts for the additive module-local scalar PODs.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_write_workflow_layout(record: u32, field: u32) -> usize {
    use std::mem::{align_of, offset_of, size_of};
    let facts: &[usize] = match record {
        0 => &[
            size_of::<WriteWorkflow>(),
            align_of::<WriteWorkflow>(),
            offset_of!(WriteWorkflow, phase),
            offset_of!(WriteWorkflow, policy),
        ],
        1 => &[
            size_of::<WriteFacts>(),
            align_of::<WriteFacts>(),
            offset_of!(WriteFacts, buffered),
            offset_of!(WriteFacts, sent),
            offset_of!(WriteFacts, capacity),
            offset_of!(WriteFacts, flags),
            offset_of!(WriteFacts, nonblock),
            offset_of!(WriteFacts, wait),
            offset_of!(WriteFacts, interrupted),
        ],
        _ => return usize::MAX,
    };
    facts.get(field as usize).copied().unwrap_or(usize::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn write_workflow_positive_observation_and_effect_order() {
        for initial_capacity in [0, 64] {
            for nonblock in [0, 1] {
                for (empty, tls, sent) in [
                    (false, false, 0),
                    (true, false, 8),
                    (true, false, 3),
                    (true, true, 0),
                ] {
                    let mut state = WriteWorkflow::default();
                    let mut facts = WriteFacts::default();
                    let mut observed = Vec::new();
                    loop {
                        let action =
                            unsafe { swr_v1_reactor_write_workflow(&mut state, 8, &mut facts) };
                        observed.push(action);
                        match action {
                            10 => facts.capacity = initial_capacity,
                            11 => {} // Native default size effect, capacity is freshly captured later.
                            12 => facts.nonblock = nonblock,
                            13 => {}
                            14 => facts.capacity = 64,
                            15 => facts.flags |= u32::from(empty),
                            16 => facts.flags |= u32::from(tls) << 1,
                            17 => facts.buffered = 2,
                            18 => facts.flags |= 4, // Normal existing Buffer, never allocate.
                            19 => facts.flags |= 8,
                            1 => facts.sent = sent,
                            5 | 6 => break,
                            _ => panic!("unexpected effect in positive profile: {action}"),
                        }
                    }
                    let mut expected = vec![10];
                    if initial_capacity == 0 {
                        expected.push(11);
                    }
                    expected.push(12);
                    if nonblock == 0 {
                        expected.push(13);
                    }
                    expected.extend([14, 15]);
                    if !empty {
                        expected.extend([17, 14, 5]);
                    } else {
                        expected.push(16);
                        if !tls {
                            expected.push(1);
                        }
                        if !tls && sent == 8 {
                            expected.push(6);
                        } else {
                            expected.extend([18, 19, 5]);
                        }
                    }
                    assert_eq!(observed, expected);
                }
            }
        }
    }
}
