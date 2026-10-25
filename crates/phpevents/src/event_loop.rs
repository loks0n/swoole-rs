//! Coupled frontend wait/exit/dispatch/shutdown policy, no Native effects.
#[repr(u32)]
enum Action {
    Done = 0,
    False = 1,
    True = 2,
    Fatal = 3,
    Reactor = 4,
    InCoroutine = 5,
    IfExit = 6,
    Bailout = 7,
    PrepareFlags = 8,
    Wait = 9,
    WarnWait = 10,
    RestoreFlags = 11,
    Free = 12,
    ClearTimers = 13,
    Stop = 14,
    OnceOn = 15,
    OnceOff = 16,
    WarnCoroutine = 17,
    Deprecated = 18,
    CoreWait = 19,
}

/// Complete frontend control, modes WAIT0/EXIT1/DISPATCH2/RSHUTDOWN3.
/// # Safety
/// Independent aligned phase initially0. Mode is constant throughout the plan;
/// observations are fresh copied booleans, except Wait's signed result. The
/// PrepareFlags observation is a copied boolean for Native's compile-time-
/// available shutdown flag suppression. Rust retains only its restore decision,
/// never Zend flags/storage. Every Native effect occurs after Rust returns;
/// Native zend_try/bailout remains outside Rust, including all error effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_loop(
    phase: *mut u32,
    mode: u32,
    observation: i64,
) -> u32 {
    use Action::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    let (action, next) = match (mode, *phase) {
        (0 | 3, 0) => (Fatal, 1),
        (0 | 3, 1) if observation != 0 => (Done, 99),
        (0 | 3, 1) | (1 | 2, 0) => (Reactor, 2),
        (0 | 1 | 3, 2) if observation == 0 => (Done, 99),
        (2, 2) if observation == 0 => (False, 99),
        (0, 2) => (InCoroutine, 3),
        (0, 3) if observation != 0 => (WarnCoroutine, 99),
        (0, 3) => (IfExit, 4),
        (0, 4) if observation != 0 => (Free, 99),
        (0 | 3, 4) => (Bailout, 5),
        (0, 5) if observation != 0 => (Free, 99),
        (0, 5) => (PrepareFlags, 6),
        (0, 6) => (Wait, if observation != 0 { 8 } else { 7 }),
        (0, 7 | 8) if observation < 0 => (WarnWait, *phase + 2),
        (0, 7 | 9) => (Free, 99),
        (0, 8 | 10) => (RestoreFlags, 11),
        (0, 11) => (Free, 99),
        (1, 2) => (ClearTimers, 3),
        (1, 3) => (Stop, 99),
        (2, 2) => (OnceOn, 3),
        (2, 3) => (Wait, 4),
        (2, 4) if observation < 0 => (WarnWait, 5),
        (2, 4 | 5) => (OnceOff, 6),
        (2, 6) => (True, 99),
        (3, 2) => (Bailout, 5),
        (3, 5) if observation == 0 => (Deprecated, 6),
        (3, 5 | 6) => (CoreWait, 99),
        _ => (Done, 99),
    };
    *phase = next;
    action as u32
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(mode: u32, observations: &[(u32, i64)]) -> Vec<u32> {
        let (mut phase, mut observation) = (0, 0);
        let mut actions = Vec::new();
        loop {
            let action = unsafe { swr_v1_phpevents_loop(&mut phase, mode, observation) };
            actions.push(action);
            if action <= 2 {
                return actions;
            }
            observation = observations
                .iter()
                .find(|(kind, _)| *kind == action)
                .map_or(0, |(_, value)| *value);
        }
    }
    #[test]
    fn wait_laziness_and_flag_restoration_are_only_metadata() {
        // No Native flags, warnings, wait/free, shutdown or callback runs here.
        assert_eq!(trace(0, &[(3, 1)]), [3, 0]);
        assert_eq!(trace(0, &[]), [3, 4, 0]);
        assert_eq!(trace(0, &[(4, 1), (5, 1)]), [3, 4, 5, 17, 0]);
        assert_eq!(trace(0, &[(4, 1), (6, 1)]), [3, 4, 5, 6, 12, 0]);
        assert_eq!(trace(0, &[(4, 1), (7, 1)]), [3, 4, 5, 6, 7, 12, 0]);
        assert_eq!(trace(0, &[(4, 1)]), [3, 4, 5, 6, 7, 8, 9, 12, 0]);
        assert_eq!(
            trace(0, &[(4, 1), (8, 1)]),
            [3, 4, 5, 6, 7, 8, 9, 11, 12, 0]
        );
        assert_eq!(
            trace(0, &[(4, 1), (8, 1), (9, -1)]),
            [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 0]
        );
    }
    #[test]
    fn exit_dispatch_and_shutdown_keep_distinct_native_boundaries() {
        assert_eq!(trace(1, &[]), [4, 0]);
        assert_eq!(trace(1, &[(4, 1)]), [4, 13, 14, 0]);
        assert_eq!(trace(2, &[]), [4, 1]);
        assert_eq!(trace(2, &[(4, 1)]), [4, 15, 9, 16, 2]);
        assert_eq!(trace(2, &[(4, 1), (9, -1)]), [4, 15, 9, 10, 16, 2]);
        assert_eq!(trace(3, &[(3, 1)]), [3, 0]);
        assert_eq!(trace(3, &[(4, 1)]), [3, 4, 7, 18, 19, 0]);
        assert_eq!(trace(3, &[(4, 1), (7, 1)]), [3, 4, 7, 19, 0]);
    }
}
