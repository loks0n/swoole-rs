//! Fiber observer selection/order over fresh copied facts; effects stay native.
#[repr(C)]
pub struct FiberStates {
    pub init: i64,
    pub waiting: i64,
    pub running: i64,
    pub end: i64,
}

/// # Safety
/// Stage is exclusive local POD initialized to zero. Kind is fixed. Observation
/// is the fresh fact requested by the previous action. For status kind, states
/// contains this native build's coroutine constants. No context/Zend pointer or
/// borrow survives a return into native observer execution.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_fiber(
    stage: *mut u32,
    kind: u32,
    observation: i64,
    states: *const FiberStates,
) -> u32 {
    let stage = unsafe { &mut *stage };
    let current = *stage;
    *stage = current.saturating_add(1);
    let action = match kind {
        0 => match current {
            0 => 1,                     // observe main context identity
            1 if observation != 0 => 2, // main is running, no state access
            1 => 3,                     // observe coroutine state once
            2 => {
                let states = unsafe { &*states };
                if observation == states.init {
                    4
                } else if observation == states.waiting {
                    5
                } else if observation == states.running {
                    2
                } else if observation == states.end {
                    6
                } else {
                    7
                }
            }
            _ => 0,
        },
        1 => match current {
            0 => 8,  // native from status publication
            1 => 9,  // native to status publication
            2 => 10, // fresh initialization-notified fact
            3 if observation != 0 => {
                *stage = 7;
                12 // already initialized: notify only
            }
            3 => 11, // first notification temporarily publishes INIT
            4 => 12,
            5 => 13, // refresh status after native observer returns
            6 => 14, // only then publish initialized flag
            _ => 0,
        },
        2 => match current {
            0 => 15, // short-circuit from presence before to presence
            1 if observation != 0 => 16,
            2 if observation != 0 => 17,
            _ => 0,
        },
        3 => match current {
            0 => 18,                     // original first context presence observation
            1 if observation != 0 => 19, // publish DEAD before switch
            2 => 20,                     // native switch notification
            3 => 21,                     // native destroy notification, fresh pointer expression
            4 => 22,                     // refresh presence after both observer effects
            5 if observation != 0 => 23, // only then native free
            _ => 0,
        },
        _ => 0,
    };
    if action == 0 {
        *stage = u32::MAX;
    }
    action
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_state_constants_and_main_short_circuit() {
        let states = FiberStates {
            init: 9,
            waiting: -3,
            running: 104,
            end: 0,
        };
        for (fact, expected) in [(9, 4), (-3, 5), (104, 2), (0, 6), (7, 7)] {
            let mut stage = 0;
            unsafe {
                assert_eq!(swr_v1_phpcoroutines_fiber(&mut stage, 0, 0, &states), 1);
                assert_eq!(swr_v1_phpcoroutines_fiber(&mut stage, 0, 0, &states), 3);
                assert_eq!(
                    swr_v1_phpcoroutines_fiber(&mut stage, 0, fact, &states),
                    expected
                );
            }
        }
        let mut stage = 0;
        unsafe {
            assert_eq!(
                swr_v1_phpcoroutines_fiber(&mut stage, 0, 0, std::ptr::null()),
                1
            );
            assert_eq!(
                swr_v1_phpcoroutines_fiber(&mut stage, 0, 1, std::ptr::null()),
                2
            );
        }
    }

    #[test]
    fn first_and_later_notification_order() {
        for (notified, expected) in [(0, vec![8, 9, 10, 11, 12, 13, 14]), (1, vec![8, 9, 10, 12])] {
            let mut stage = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe {
                    swr_v1_phpcoroutines_fiber(&mut stage, 1, notified, std::ptr::null())
                };
                if action == 0 {
                    break;
                }
                actions.push(action);
            }
            assert_eq!(actions, expected);
        }
        for (from, to, expected) in [
            (0, 0, vec![15]),
            (0, 1, vec![15]),
            (1, 0, vec![15, 16]),
            (1, 1, vec![15, 16, 17]),
        ] {
            let mut stage = 0;
            let mut observation = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe {
                    swr_v1_phpcoroutines_fiber(&mut stage, 2, observation, std::ptr::null())
                };
                if action == 0 {
                    break;
                }
                actions.push(action);
                observation = if action == 15 { from } else { to };
            }
            assert_eq!(actions, expected);
        }
    }
    #[test]
    fn destruction_short_circuits_and_refreshes_after_observers() {
        for (initial, refreshed, expected) in [
            (0, 0, vec![18]),
            (0, 1, vec![18]),
            (1, 0, vec![18, 19, 20, 21, 22]),
            (1, 1, vec![18, 19, 20, 21, 22, 23]),
        ] {
            let mut stage = 0;
            let mut observation = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe {
                    swr_v1_phpcoroutines_fiber(&mut stage, 3, observation, std::ptr::null())
                };
                if action == 0 {
                    break;
                }
                actions.push(action);
                observation = if action == 18 { initial } else { refreshed };
            }
            assert_eq!(actions, expected);
        }
    }
}
