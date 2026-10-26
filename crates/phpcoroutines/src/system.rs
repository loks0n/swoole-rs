//! System frontend path admission and platform-provided file mode selection.
#[repr(C)]
pub struct FileConfig {
    pub lock: i32,
    pub append_mask: i32,
    pub base_open: i32,
    pub append_open: i32,
    pub truncate_open: i32,
}

#[repr(C)]
pub struct FilePlan {
    pub accepted: u8,
    pub lock: i32,
    pub open: i32,
}

/// # Safety
/// `config` is readable for this call. It carries this native platform's constants.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_system_file(
    nonempty: u8,
    flags: i64,
    config: *const FileConfig,
) -> FilePlan {
    // SAFETY: per this function's `# Safety` contract, `config` is live, aligned and initialized.
    let config = unsafe { &*config };
    FilePlan {
        accepted: u8::from(nonempty != 0),
        lock: (flags & i64::from(config.lock)) as i32,
        open: config.base_open
            | if flags & i64::from(config.append_mask) != 0 {
                config.append_open
            } else {
                config.truncate_open
            },
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_system_sleep(seconds: f64, minimum: f64) -> u8 {
    // Preserve the original comparison, including its unordered (NaN) behavior.
    u8::from(seconds >= minimum || seconds.is_nan() || minimum.is_nan())
}

/// Ordered hostname/family admission; platform address-family values stay native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_system_address(
    length: usize,
    family: i64,
    ipv4: i64,
    ipv6: i64,
) -> u32 {
    if length == 0 {
        1
    } else if family != ipv4 && family != ipv6 {
        2
    } else {
        0
    }
}

#[repr(C)]
pub struct ResultState {
    pub index: usize,
    pub started: u8,
}
#[repr(C)]
pub struct ResultPlan {
    pub action: u32,
    pub key: *const std::ffi::c_char,
    pub index: usize,
    pub value: i64,
}

/// Whole ordinary System result selection/publication order. Native payloads and
/// platform stat fields stay native; only copied status/size facts enter Rust.
/// # Safety
/// For cursor kinds (4..=9), state is exclusive zero-initialized POD.
/// For scalar kinds (0..=3), state may be null. Facts are refreshed after each
/// requested native effect. No native payload pointer enters Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_system_complete(
    kind: u32,
    state: *mut ResultState,
    result: i64,
    count: usize,
) -> ResultPlan {
    let mut plan = ResultPlan {
        action: 0,
        key: std::ptr::null(),
        index: 0,
        value: result,
    };
    match kind {
        0 => {
            plan.action = 2;
            plan.value = i64::from(result == 0);
        }
        1 => plan.action = if result != 0 { 4 } else { 1 },
        2 => plan.action = if result < 0 { 1 } else { 3 },
        3 => plan.action = if count == 0 { 1 } else { 4 },
        4 | 5 => {
            // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
            let state = unsafe { &mut *state };
            if state.started == 0 {
                state.started = 1;
                plan.action = if kind == 4 && count == 0 { 1 } else { 5 };
            } else if kind == 4 && state.index < count {
                plan.action = 6;
                plan.index = state.index;
                state.index += 1;
            } else if kind == 5 {
                const KEYS: [&[u8]; 11] = [
                    b"bsize\0",
                    b"frsize\0",
                    b"blocks\0",
                    b"bfree\0",
                    b"bavail\0",
                    b"files\0",
                    b"ffree\0",
                    b"favail\0",
                    b"fsid\0",
                    b"flag\0",
                    b"namemax\0",
                ];
                if let Some(key) = KEYS.get(state.index) {
                    plan.action = 7;
                    plan.index = state.index;
                    plan.key = key.as_ptr().cast();
                    state.index += 1;
                }
            }
        }
        6..=9 => {
            // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
            let state = unsafe { &mut *state };
            let phase = state.index;
            state.index = phase.saturating_add(1);
            match kind {
                6 | 7 => match phase {
                    0 if kind == 6 => plan.action = if result == 0 { 1 } else { 8 },
                    0 => plan.action = if result < 0 { 9 } else { 10 },
                    1 => plan.action = if kind == 7 && result <= 0 { 1 } else { 5 },
                    2..=4 => {
                        const EXEC: [&[u8]; 3] = [b"code\0", b"signal\0", b"output\0"];
                        const WAIT: [&[u8]; 3] = [b"pid\0", b"code\0", b"signal\0"];
                        plan.action = 7;
                        plan.index = phase - 2;
                        plan.key = if kind == 6 { EXEC } else { WAIT }[plan.index]
                            .as_ptr()
                            .cast();
                    }
                    _ => {}
                },
                8 => match phase {
                    0 => plan.action = if result == -1 { 13 } else { 3 },
                    1 if result != 0 => {
                        state.index = 3;
                        plan.action = 11;
                    }
                    1 => plan.action = 14,
                    2 if result != 0 => plan.action = 12,
                    2 => {
                        state.index = 4;
                        plan.action = 15;
                    }
                    3 => plan.action = 15,
                    4 => plan.action = 1,
                    _ => {}
                },
                9 => match phase {
                    0 => plan.action = if result < 0 { 17 } else { 16 },
                    1 => plan.action = if result < 0 { 1 } else { 3 },
                    _ => {}
                },
                _ => unreachable!(),
            }
        }
        _ => plan.action = 1,
    }
    plan
}

#[cfg(test)]
mod control_tests {
    use super::*;
    fn next(kind: u32, state: &mut ResultState, fact: i64) -> ResultPlan {
        unsafe { swr_v1_phpcoroutines_system_complete(kind, state, fact, 0) }
    }
    fn state() -> ResultState {
        ResultState {
            index: 0,
            started: 0,
        }
    }

    #[test]
    fn native_signal_error_short_circuit_and_fresh_final_errno() {
        // Only -1 takes the native error path. -2 and zero are published longs.
        for value in [-2, 0, 1, i32::MAX as i64] {
            assert_eq!(next(8, &mut state(), value).action, 3);
        }
        for (busy, invalid, actions) in [
            (true, false, vec![13, 11, 15, 1]),
            (false, true, vec![13, 14, 12, 15, 1]),
            (false, false, vec![13, 14, 15, 1]),
        ] {
            let mut state = state();
            let mut fact = -1;
            let mut actual = Vec::new();
            loop {
                let plan = next(8, &mut state, fact);
                actual.push(plan.action);
                match plan.action {
                    13 => fact = i64::from(busy),
                    14 => fact = i64::from(invalid),
                    1 => break,
                    // Warning and final errno actions do not carry/cache an
                    // error value; native code obtains it freshly afterward.
                    _ => fact = 901,
                }
            }
            assert_eq!(actual, actions);
        }
    }

    #[test]
    fn wait_and_exec_publication_and_event_boundaries() {
        for (kind, first, accepted, keys) in [
            (6, 1, 8, [c"code", c"signal", c"output"]),
            (7, -1, 9, [c"pid", c"code", c"signal"]),
            (7, 1, 10, [c"pid", c"code", c"signal"]),
        ] {
            let mut state = state();
            assert_eq!(next(kind, &mut state, first).action, accepted);
            assert_eq!(next(kind, &mut state, 74).action, 5);
            for (index, key) in keys.into_iter().enumerate() {
                let field = next(kind, &mut state, 74);
                assert_eq!(field.action, 7);
                assert_eq!(field.index, index);
                assert_eq!(unsafe { std::ffi::CStr::from_ptr(field.key) }, key);
            }
            assert_eq!(next(kind, &mut state, 74).action, 0);
        }
        assert_eq!(next(6, &mut state(), 0).action, 1);
        for pid in [0, -1] {
            let mut state = state();
            assert_eq!(next(7, &mut state, -1).action, 9);
            assert_eq!(next(7, &mut state, pid).action, 1);
        }
        assert_eq!(next(9, &mut state(), -1).action, 17);
        for result in [-1, 0, i64::MAX] {
            let mut state = state();
            assert_eq!(next(9, &mut state, 0).action, 16);
            let plan = next(9, &mut state, result);
            assert_eq!(plan.action, if result < 0 { 1 } else { 3 });
            assert_eq!(plan.value, result);
        }
    }
}
