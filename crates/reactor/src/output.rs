//! Ordinary Socket output progression. All effects and observations happen in
//! Native after each completed pure value call; no pointer, borrow, queue or
//! payload owner enters Rust. The separately selected Native repair prefix is
//! evaluated before its sendfile result is supplied here.
#[repr(C)]
pub struct ReactorOutputAction {
    pub phase: u32,
    pub action: i32,
    pub value: i64,
}
fn step(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
/// DATA actions:0 done,1 send,2 pop/return,3 classify,4 warn/return,
///5 close-wait/return-error,6 send-wait/return-error,7 refresh offset,
///8 publish offset/return,9 publish offset+send-wait/return-error.
/// `requested` is the unchanged scalar returned with action1; offset is freshly
/// observed only at phase3. Native SW_WAIT2/SW_CLOSE3/SW_ERROR4 are asserted there.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_data(
    phase: u32,
    requested: u32,
    length: u32,
    offset: u32,
    result: isize,
    error: i32,
) -> ReactorOutputAction {
    match phase {
        0 => {
            let remaining = length.wrapping_sub(offset);
            step(1, if remaining == 0 { 2 } else { 1 }, remaining.into())
        }
        1 if result < 0 => step(2, 3, 0),
        1 if result as u64 == u64::from(requested) => step(4, 2, 0),
        1 => step(3, 7, 0),
        2 => step(
            4,
            match error {
                2 => 6,
                3 => 5,
                4 => 4,
                _ => 0,
            },
            0,
        ),
        3 => step(
            4,
            if (result as u64) < u64::from(requested) {
                9
            } else {
                8
            },
            offset.wrapping_add(result as u32).into(),
        ),
        4 => step(4, 0, 0),
        _ => step(phase, -1, 0),
    }
}
/// File actions:0 done,1 cork,2 publish cork flag,3 sendfile,4 classify,
///5 warn,6 close-wait/return-error,7 send-wait/return-error,8 timestamp,
///9 uncork,10 pop/return,11 refresh facts. Flags:timer1,cork-result2.
/// Fields are supplied only at their requested phase:0/9 corked,10 cork range,
///11 timer presence,5 completion range. Effects never run within this call.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_file(
    phase: u32,
    corked: i32,
    begin: i64,
    end: i64,
    cork_min: i64,
    result: isize,
    error: i32,
    flags: u32,
) -> ReactorOutputAction {
    match phase {
        0 if corked == 0 => step(10, 11, 0),
        0 => step(3, 3, 0),
        10 if end.wrapping_sub(begin) > cork_min => step(1, 1, 0),
        10 => step(2, 2, -1),
        1 => step(2, 2, if flags & 2 != 0 { 1 } else { -1 }),
        2 => step(3, 3, 0),
        3 if result <= 0 => step(4, 4, 0),
        3 => step(11, 11, 0),
        4 => match error {
            4 => step(6, 5, 0),
            3 => step(12, 6, 0),
            2 => step(12, 7, 0),
            _ => step(5, 11, 0),
        },
        11 => step(5, if flags & 1 != 0 { 8 } else { 11 }, 0),
        5 if begin != end => step(12, 0, 0),
        5 => step(9, 11, 0),
        9 if corked == 1 => step(7, 9, 0),
        9 | 6 | 8 => step(12, 10, 0),
        7 => step(8, 2, 0),
        12 => step(12, 0, 0),
        _ => step(phase, -1, 0),
    }
}
/// Request actions:0 done,1 allocate request,2 check Native parameters,
///3 allocate/publish buffer,4 allocate chunk,5 release/publish request,
///6 publish destructor,7 return-error,8 refresh out-buffer presence.
/// Native owns the unique_ptr and all failure/exception cleanup. Flags:buffer1.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_request(
    phase: u32,
    validation: i32,
    flags: u32,
) -> ReactorOutputAction {
    match phase {
        0 => step(1, 1, 0),
        1 => step(2, 2, 0),
        2 if validation == 0 => step(8, 7, 0),
        2 => step(3, 8, 0),
        3 if flags & 1 == 0 => step(4, 3, 0),
        3 | 4 => step(5, 4, 0),
        5 => step(6, 5, 0),
        6 => step(7, 6, 0),
        7 | 8 => step(8, 0, 0),
        _ => step(phase, -1, 0),
    }
}
/// The subtraction has the original defined off_t domain. Native checks its
/// signed off_t fits i64. Casting/min preserve the original size_t conversion;
/// out-of-domain signed overflow is not claimed as Native parity.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_chunk(begin: i64, end: i64, limit: usize) -> usize {
    (end.wrapping_sub(begin) as usize).min(limit)
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_layout(field: u32) -> usize {
    match field {
        0 => std::mem::size_of::<ReactorOutputAction>(),
        1 => std::mem::align_of::<ReactorOutputAction>(),
        2 => std::mem::offset_of!(ReactorOutputAction, value),
        _ => usize::MAX,
    }
}
/// Parameter actions:0 return true,1 stat,2 open warning/false,3 stat warning/
///false,4 empty warning/false,5 publish end,6 range warning/false,7 observe size.
/// Native gets the path/ready first. Stat storage and every warning stay Native.
/// End is reobserved only after its publication; signed overflow is outside the
/// pinned defined domain, not inferred Native parity.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_output_parameters(
    phase: u32,
    observed: i32,
    size: i64,
    begin: i64,
    length: usize,
    end: i64,
) -> ReactorOutputAction {
    match phase {
        0 => step(1, if observed != 0 { 1 } else { 2 }, 0),
        1 => step(2, if observed != 0 { 7 } else { 3 }, 0),
        2 if size == 0 => step(4, 4, 0),
        2 => step(
            3,
            5,
            if length == 0 {
                size
            } else {
                begin.wrapping_add(length as i64)
            },
        ),
        3 => step(4, if begin < 0 || end > size { 6 } else { 0 }, 0),
        _ => step(phase, -1, 0),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn output_positive_data_file_and_request_order() {
        for length in [0usize, 1, 7, 29] {
            assert_eq!(
                swr_v1_reactor_output_parameters(0, 1, 0, 2, length, 0).action,
                1
            );
            assert_eq!(
                swr_v1_reactor_output_parameters(1, 1, 0, 2, length, 0).action,
                7
            );
            let end = if length == 0 { 31 } else { length as i64 + 2 };
            let plan = swr_v1_reactor_output_parameters(2, 1, 31, 2, length, 0);
            assert_eq!((plan.action, plan.value), (5, end));
            assert_eq!(
                swr_v1_reactor_output_parameters(3, 1, 31, 2, length, end).action,
                0
            );
        }
        for length in [1u32, 7, 31] {
            for sent in 1..=length {
                let send = swr_v1_reactor_output_data(0, 0, length + 3, 3, 0, 0);
                assert_eq!((send.action, send.value), (1, length.into()));
                let outcome =
                    swr_v1_reactor_output_data(send.phase, length, 0, 0, sent as isize, 0);
                if sent == length {
                    assert_eq!(outcome.action, 2);
                } else {
                    assert_eq!((outcome.phase, outcome.action), (3, 7));
                    let publish = swr_v1_reactor_output_data(3, length, 0, 3, sent as isize, 0);
                    assert_eq!((publish.action, publish.value), (9, i64::from(sent + 3)));
                }
            }
        }
        let file = |phase, corked, begin, end, flags| {
            swr_v1_reactor_output_file(phase, corked, begin, end, 8, 1, 0, flags)
        };
        assert_eq!(
            (file(0, 0, 0, 0, 0).phase, file(0, 0, 0, 0, 0).action),
            (10, 11)
        );
        assert_eq!(file(10, 0, 0, 9, 0).action, 1);
        assert_eq!(file(1, 0, 0, 0, 2).value, 1);
        assert_eq!(file(10, 0, 0, 8, 0).value, -1);
        assert_eq!(file(2, 0, 0, 0, 0).action, 3);
        assert_eq!(file(3, 0, 0, 0, 0).phase, 11);
        assert_eq!(file(11, 0, 0, 0, 1).action, 8);
        assert_eq!(file(5, 0, 1, 9, 0).action, 0);
        assert_eq!(file(5, 0, 9, 9, 0).phase, 9);
        assert_eq!(file(9, 1, 0, 0, 0).action, 9);
        assert_eq!(
            (file(7, 0, 0, 0, 0).action, file(7, 0, 0, 0, 0).value),
            (2, 0)
        );
        assert_eq!(file(8, 0, 0, 0, 0).action, 10);
        assert_eq!(swr_v1_reactor_output_chunk(3, 17, 8), 8);
        assert_eq!(swr_v1_reactor_output_chunk(3, 7, 8), 4);
        for has_buffer in [0, 1] {
            let mut phase = 0;
            let mut actions = Vec::new();
            loop {
                let next = swr_v1_reactor_output_request(phase, 1, has_buffer);
                phase = next.phase;
                actions.push(next.action);
                if next.action == 0 {
                    break;
                }
            }
            assert_eq!(
                actions,
                if has_buffer == 0 {
                    vec![1, 2, 8, 3, 4, 5, 6, 0]
                } else {
                    vec![1, 2, 8, 4, 5, 6, 0]
                }
            );
        }
    }
}
