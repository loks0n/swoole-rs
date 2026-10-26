//! Exit frontend policy; Zend operands, exceptions and termination stay Native.
#[repr(C)]
pub struct ExitState {
    pub phase: u32,
    pub flags: i64,
}
#[repr(C)]
pub struct ExitConfig {
    pub coroutine: i64,
    pub server: i64,
    pub unused: u32,
    pub constant: u32,
}
#[repr(C)]
pub struct ExitPlan {
    pub action: u32,
    pub flags: i64,
}

fn legacy(state: &mut ExitState, config: &ExitConfig, phase: u32, fact: i64) -> u32 {
    match phase {
        4 if state.flags == 0 => 0,
        4 => 4, // Native legacy operand scope, after captured flags
        5 => 6, // fresh operand type
        6 if fact == i64::from(config.unused) => {
            state.phase = 12;
            9
        }
        6 if fact == i64::from(config.constant) => 7,
        6 => 8,
        7 => 10, // fresh reference fact, after Native operand lookup
        8 if fact != 0 => 11,
        8 | 9 => {
            state.phase = 12;
            12
        }
        12 => 13,
        13 => 14,
        14 => 15,
        _ => 0,
    }
}

fn modern(state: &mut ExitState, phase: u32, fact: i64) -> u32 {
    match phase {
        4 => 5, // Native parser runs after both flag observations
        5 if state.flags == 0 => {
            state.phase = 10;
            21
        }
        5 => 16,
        6 => {
            if fact != 0 {
                17
            } else {
                18
            }
        }
        7 => 14,
        8 => 16, // fresh message presence after Native throw/property effects
        9 => {
            state.phase = 15;
            if fact != 0 { 19 } else { 20 }
        }
        10 if fact != 0 => 0,
        10 => 16,
        11 if fact != 0 => 22,
        11 | 12 => 23,
        _ => 0,
    }
}

/// # Safety
/// State is exclusive zero-initialized local POD; config is immutable Native
/// constants for the invocation. Kind is legacy(0)/modern(1). Fact is the fresh
/// scalar requested by the previous action. No Zend/server/context/string
/// pointer enters Rust and no borrow/frame crosses Native effects or bailout.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_exit(
    state: *mut ExitState,
    config: *const ExitConfig,
    kind: u32,
    fact: i64,
) -> ExitPlan {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    // SAFETY: per this function's `# Safety` contract, `config` is live, aligned and initialized.
    let config = unsafe { &*config };
    loop {
        let phase = state.phase;
        state.phase = phase.saturating_add(1);
        let action = match phase {
            0 => 1,
            1 => {
                if fact != 0 {
                    state.flags |= config.coroutine;
                }
                2
            }
            2 if fact != 0 => 3,
            2 => {
                state.phase = 4;
                continue;
            }
            3 => {
                if fact != 0 {
                    state.flags |= config.server;
                }
                continue;
            }
            _ if kind == 0 => legacy(state, config, phase, fact),
            _ if kind == 1 => modern(state, phase, fact),
            _ => 0,
        };
        if action == 0 {
            state.phase = u32::MAX;
        }
        return ExitPlan {
            action,
            flags: state.flags,
        };
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn step(state: &mut ExitState, kind: u32, fact: i64) -> ExitPlan {
        let config = ExitConfig {
            coroutine: 0x40,
            server: 0x100,
            unused: 7,
            constant: 12,
        };
        unsafe { swr_v1_phpcoroutines_exit(state, &config, kind, fact) }
    }
    fn flags(kind: u32, current: i64, server: i64, started: i64) -> (ExitState, ExitPlan) {
        let mut state = ExitState { phase: 0, flags: 0 };
        assert_eq!(step(&mut state, kind, 0).action, 1);
        assert_eq!(step(&mut state, kind, current).action, 2);
        let plan = step(&mut state, kind, server);
        if server == 0 {
            (state, plan)
        } else {
            assert_eq!(plan.action, 3);
            let next = step(&mut state, kind, started);
            (state, next)
        }
    }
    #[test]
    fn native_constants_and_short_circuit_flags() {
        for kind in [0, 1] {
            for (co, server, started, expected) in [
                (0, 0, 0, 0),
                (1, 0, 0, 0x40),
                (0, 1, 0, 0),
                (0, 1, 1, 0x100),
                (1, 1, 1, 0x140),
            ] {
                let (_, plan) = flags(kind, co, server, started);
                assert_eq!(plan.flags, expected);
                assert_eq!(
                    plan.action,
                    if kind == 0 {
                        if expected == 0 { 0 } else { 4 }
                    } else {
                        5
                    }
                );
            }
        }
    }
    #[test]
    fn legacy_operand_reference_and_property_order() {
        for (operand, reference, expected) in [
            (7, 0, vec![6, 9, 13, 14, 15, 0]),
            (12, 0, vec![6, 7, 10, 12, 13, 14, 15, 0]),
            (12, 1, vec![6, 7, 10, 11, 12, 13, 14, 15, 0]),
            (19, 1, vec![6, 8, 10, 11, 12, 13, 14, 15, 0]),
        ] {
            let (mut state, _) = flags(0, 1, 0, 0);
            let mut result = Vec::new();
            let mut fact = 0;
            loop {
                let plan = step(&mut state, 0, fact);
                result.push(plan.action);
                fact = if plan.action == 6 {
                    operand
                } else if plan.action == 10 {
                    reference
                } else {
                    0
                };
                if plan.action == 0 {
                    break;
                }
            }
            assert_eq!(result, expected);
        }
    }
    #[test]
    fn modern_parsing_snapshot_fresh_message_and_original_handler() {
        for ctor_message in [0, 1] {
            for status_message in [0, 1] {
                let (mut state, _) = flags(1, 1, 0, 0);
                assert_eq!(step(&mut state, 1, 0).action, 16);
                assert_eq!(
                    step(&mut state, 1, ctor_message).action,
                    if ctor_message != 0 { 17 } else { 18 }
                );
                assert_eq!(step(&mut state, 1, 0).action, 14);
                assert_eq!(step(&mut state, 1, 0).action, 16);
                assert_eq!(
                    step(&mut state, 1, status_message).action,
                    if status_message != 0 { 19 } else { 20 }
                );
                assert_eq!(step(&mut state, 1, 0).action, 0);
            }
        }
        for (success, message, expected) in [
            (1, 0, vec![0]),
            (0, 0, vec![16, 23]),
            (0, 1, vec![16, 22, 23]),
        ] {
            let (mut state, _) = flags(1, 0, 0, 0);
            assert_eq!(step(&mut state, 1, 0).action, 21);
            let mut result = Vec::new();
            let mut fact = success;
            loop {
                let p = step(&mut state, 1, fact);
                result.push(p.action);
                if matches!(p.action, 0 | 23) {
                    break;
                }
                fact = message;
            }
            assert_eq!(result, expected);
        }
    }
}
