//! Complete reactor admission/readiness; all server/reactor/Zend effects Native.
#[repr(u32)]
enum Init {
    Error = 0,
    Ok = 1,
    Cli = 2,
    Server = 3,
    TaskWorker = 4,
    TaskCoroutine = 5,
    Manager = 6,
    Reactor = 7,
    Trace = 8,
    Create = 9,
    RegisterShutdown = 10,
    FreshReactor = 11,
    UserCondition = 12,
    HasCondition = 13,
    SetCondition = 14,
    WarnCli = 15,
    WarnTask = 16,
    WarnManager = 17,
    WarnCreate = 18,
}

/// Full original process admission and lazy reactor/exit-condition publication.
/// # Safety
/// Independent aligned phase0; all observations are freshly read Native booleans,
/// except Create's signed result. Native completes every requested effect after
/// return. No Server/Reactor/Callable/Zend pointer or borrowed state enters Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_reactor_init(phase: *mut u32, observation: i64) -> u32 {
    use Init::{
        Cli, Create, Error, FreshReactor, HasCondition, Manager, Ok, Reactor, RegisterShutdown,
        Server, SetCondition, TaskCoroutine, TaskWorker, Trace, UserCondition, WarnCli, WarnCreate,
        WarnManager, WarnTask,
    };
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Error as u32;
    };
    let (action, next) = match *phase {
        0 => (Cli, 1),
        1 if observation == 0 => (WarnCli, 99),
        1 => (Server, 2),
        2 if observation == 0 => (Reactor, 6),
        2 => (TaskWorker, 3),
        3 if observation != 0 => (TaskCoroutine, 4),
        3 => (Manager, 5),
        4 if observation == 0 => (WarnTask, 99),
        4 => (Manager, 5),
        5 if observation != 0 => (WarnManager, 99),
        5 => (Reactor, 6),
        6 if observation == 0 => (Trace, 7),
        6 => (FreshReactor, 10),
        7 => (Create, 8),
        8 if observation < 0 => (WarnCreate, 99),
        8 => (RegisterShutdown, 9),
        9 => (FreshReactor, 10),
        10 if observation == 0 => (Ok, 98),
        10 => (UserCondition, 11),
        11 if observation == 0 => (Ok, 98),
        11 => (HasCondition, 12),
        12 if observation != 0 => (Ok, 98),
        12 => (SetCondition, 13),
        13 | 98 => (Ok, 98),
        _ => (Error, 99),
    };
    *phase = next;
    action as u32
}

/// Coupled readiness registration at the original three-handler boundary.
/// # Safety
/// Independent aligned phase0. Native reactor readiness/check and each handler
/// publication complete outside Rust. Existing Read handler means no writes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_handlers(phase: *mut u32, observation: u8) -> u32 {
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    let (action, next) = match *phase {
        0 => (1, 1), // Native php_swoole_check_reactor
        1 => (2, 2), // Existing readable handler?
        2 if observation != 0 => (0, 99),
        2 => (3, 3), // Read, Write, Error publication, original order
        3 => (4, 4),
        4 => (5, 99),
        _ => (0, 99),
    };
    *phase = next;
    action
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(values: &[(u32, i64)]) -> Vec<u32> {
        let (mut phase, mut observation) = (0, 0);
        let mut actions = Vec::new();
        loop {
            let action = unsafe { swr_v1_phpevents_reactor_init(&raw mut phase, observation) };
            actions.push(action);
            if action <= 1 {
                return actions;
            }
            observation = values
                .iter()
                .find(|(kind, _)| *kind == action)
                .map_or(0, |(_, value)| *value);
        }
    }
    #[test]
    fn process_guards_preserve_short_circuit_order() {
        assert_eq!(trace(&[]), [2, 15, 0]);
        assert_eq!(trace(&[(2, 1), (3, 1), (4, 1)]), [2, 3, 4, 5, 16, 0]);
        assert_eq!(trace(&[(2, 1), (3, 1), (6, 1)]), [2, 3, 4, 6, 17, 0]);
    }
    #[test]
    fn lazy_creation_and_fresh_condition_observation() {
        assert_eq!(trace(&[(2, 1)]), [2, 3, 7, 8, 9, 10, 11, 1]);
        assert_eq!(trace(&[(2, 1), (9, -1)]), [2, 3, 7, 8, 9, 18, 0]);
        assert_eq!(
            trace(&[(2, 1), (7, 1), (11, 1), (12, 1)]),
            [2, 3, 7, 11, 12, 13, 14, 1]
        );
        assert_eq!(
            trace(&[
                (2, 1),
                (3, 1),
                (4, 1),
                (5, 1),
                (7, 1),
                (11, 1),
                (12, 1),
                (13, 1)
            ]),
            [2, 3, 4, 5, 6, 7, 11, 12, 13, 1]
        );
    }
    #[test]
    fn handler_registration_is_all_or_none_in_native_order() {
        for present in [0, 1] {
            let mut phase = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe { swr_v1_phpevents_handlers(&raw mut phase, present) };
                actions.push(action);
                if action == 0 {
                    break;
                }
            }
            assert_eq!(
                actions,
                if present == 0 {
                    vec![1, 2, 3, 4, 5, 0]
                } else {
                    vec![1, 2, 0]
                }
            );
        }
    }
}
