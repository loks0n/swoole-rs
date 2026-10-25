//! Cancellation and timer frontend policy; Native Zend/core/timer effects only.
#[repr(C)]
pub struct ControlPlan {
    pub action: u32,
    pub value: i64,
}

/// # Safety
/// Stage is invocation-local exclusive zeroed POD, kind and timeout stay fixed.
/// Observation is the fresh requested presence/result fact. No object, context,
/// exception, executor, Coroutine or timer-node pointer enters Rust. No Rust
/// frame/borrow spans Native allocation, object mutation, cancellation or callback.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_control(
    stage: *mut u32,
    kind: u32,
    observation: i64,
    timeout: f64,
) -> ControlPlan {
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        let mut plan = ControlPlan {
            action: 0,
            value: 0,
        };
        if current == 98 {
            plan.action = 4;
            return plan;
        }
        plan.action = match kind {
            0 => match current {
                0 => 2,
                1 if observation == 0 => {
                    *stage = 98;
                    3
                }
                1 => 17,
                2 => {
                    if observation != 0 {
                        16
                    } else {
                        4
                    }
                }
                _ => 0,
            },
            1 => match current {
                0 => 1,
                1 if observation == 0 => {
                    *stage = 98;
                    3
                }
                1 => 5,
                2 if observation != 0 => 6,
                2 => {
                    *stage = 4;
                    continue;
                }
                3 if observation != 0 => {
                    *stage = 98;
                    7
                }
                3 => continue,
                4 => 8,
                5 => 9,
                6 if observation != 0 => 10,
                6 => continue,
                7 => 11,
                8 => 12,
                9 => 13,
                10 => 14,
                11 => 15,
                12 => 16,
                _ => 0,
            },
            2 => match current {
                0 if timeout == 0.0 || observation == 0 => 4,
                0 => 18,
                1 => {
                    // Preserve Native `(long) timeout * 1000`: truncate BEFORE
                    // multiplication, including subsecond nonzero -> zero ms.
                    // Native nonfinite/out-of-long-range/overflow cases have no
                    // defined C++ result and remain outside the parity domain.
                    #[allow(clippy::unnecessary_cast)]
                    {
                        plan.value = (timeout as std::ffi::c_long).wrapping_mul(1000) as i64;
                    }
                    19
                }
                2 => 16,
                _ => 0,
            },
            3 => match current {
                0 if observation != 0 => 20,
                _ => 0,
            },
            4 | 5 => match current {
                0 => 5, // fresh Native EG(exception) presence
                1 if observation == 0 => 4,
                1 if kind == 5 => 6, // recovery enabled: class fact
                1 => {
                    *stage = 5;
                    23
                } // Native exception_error then true
                2 if observation != 0 => 21, // recover: Native release
                2 => {
                    *stage = 5;
                    23
                }
                3 => 22, // clear only after release returns
                4 => 4,
                5 => 16,
                _ => 0,
            },
            6 => match current {
                0 => 24, // fresh core count
                1 if observation == 0 => 0,
                1 => 25, // fatal status before any reactor access
                2 if observation != 0 => 0,
                2 => 26,                     // Native first reactor presence
                3 if observation != 0 => 27, // Native second reactor lookup
                3 => {
                    *stage = 5;
                    28
                } // no reactor: library fact next
                4 if observation != 0 => 0,
                4 => 28,
                5 if observation != 0 => 29,
                5 => 30,
                _ => 0,
            },
            7 => match current {
                0 => 31, // close callback presence
                1 if observation != 0 => 32,
                1 => {
                    *stage = 3;
                    33
                }
                2 => 33, // free only after Native callback returns
                _ => 0,
            },
            8 => match current {
                0 => 34, // request shutdown phase before executor access
                1 if observation != 0 => 35,
                1 => {
                    *stage = 5;
                    39
                }
                2 => 36,
                3 if observation != 0 => 37,
                3 => {
                    *stage = 5;
                    39
                }
                4 if observation != 0 => {
                    *stage = 7;
                    38
                }
                4 => 39,
                5 if observation > 0 => 40,
                5 | 7 => 4,
                _ => 0,
            },
            9 => match current {
                0 => 41,
                1 if observation != 0 => 42,
                1 => {
                    *stage = 5;
                    45
                }
                2 => 43,
                3 => 44,
                4 => 45,
                _ => 0,
            },
            10 => match current {
                0 => 26,
                1 if observation != 0 => 46,
                1 => {
                    *stage = 4;
                    48
                }
                2 => 47,
                3 => 48,
                _ => 0,
            },
            _ => 0,
        };
        return plan;
    }
}

/// # Safety
/// Name points to the same readable ten-byte window required by the pinned
/// Native `memcmp(name, "__destruct", 10)`. No length read or terminator scan is
/// introduced. The Native name owner stays valid; no borrow spans an effect.
/// Short/unreadable windows have no defined original result and are unqualified.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_create_destructor(name: *const u8) -> u8 {
    u8::from(unsafe { std::slice::from_raw_parts(name, 10) } == b"__destruct")
}

#[cfg(test)]
mod tests {
    use super::*;
    unsafe fn trace(kind: u32, facts: &[i64]) -> Vec<u32> {
        let mut stage = 0;
        let mut fact = 0;
        let mut facts = facts.iter();
        let mut actions = Vec::new();
        loop {
            let plan = unsafe { swr_v1_phpcoroutines_control(&mut stage, kind, fact, 0.0) };
            if plan.action == 0 {
                break;
            }
            actions.push(plan.action);
            if matches!(plan.action, 1 | 2 | 5 | 6 | 9 | 17) {
                fact = *facts.next().unwrap();
            }
            if matches!(plan.action, 4 | 16) {
                break;
            }
        }
        assert!(facts.next().is_none());
        actions
    }
    #[test]
    fn cancellation_short_circuit_and_exception_effect_order() {
        for (kind, facts, expected) in [
            (0, vec![0], vec![2, 3, 4]),
            (0, vec![1, 0], vec![2, 17, 4]),
            (0, vec![1, 1], vec![2, 17, 16]),
            (1, vec![0], vec![1, 3, 4]),
            (1, vec![1, 1, 1], vec![1, 5, 6, 7, 4]),
            (1, vec![1, 0, 0], vec![1, 5, 8, 9, 11, 12, 13, 14, 15, 16]),
            (
                1,
                vec![1, 1, 0, 1],
                vec![1, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16],
            ),
        ] {
            assert_eq!(unsafe { trace(kind, &facts) }, expected);
        }
    }
    #[test]
    fn timeout_truncation_admission_and_callback_fact_only() {
        for (timeout, present, expected) in [
            (0.0, 1, 4),
            (-0.0, 1, 4),
            (1.0, 0, 4),
            (0.5, 1, 18),
            (-1.5, 1, 18),
        ] {
            let mut stage = 0;
            assert_eq!(
                unsafe { swr_v1_phpcoroutines_control(&mut stage, 2, present, timeout) }.action,
                expected
            );
        }
        for (timeout, milliseconds) in [
            (0.5, 0),
            (-0.5, 0),
            (1.9, 1000),
            (-1.9, -1000),
            (120.0, 120000),
        ] {
            let mut stage = 0;
            assert_eq!(
                unsafe { swr_v1_phpcoroutines_control(&mut stage, 2, 1, timeout) }.action,
                18
            );
            let plan = unsafe { swr_v1_phpcoroutines_control(&mut stage, 2, 0, timeout) };
            assert_eq!((plan.action, plan.value), (19, milliseconds));
            assert_eq!(
                unsafe { swr_v1_phpcoroutines_control(&mut stage, 2, 0, timeout) }.action,
                16
            );
        }
        for (present, action) in [(0, 0), (1, 20)] {
            let mut stage = 0;
            assert_eq!(
                unsafe { swr_v1_phpcoroutines_control(&mut stage, 3, present, 0.0) }.action,
                action
            );
        }
    }
    #[test]
    fn terminal_policy_uses_fresh_facts_without_native_effects() {
        for (kind, facts, expected) in [
            (4, vec![0], vec![5, 4]),
            (4, vec![1], vec![5, 23, 16]),
            (5, vec![0], vec![5, 4]),
            (5, vec![1, 0], vec![5, 6, 23, 16]),
            (5, vec![1, 1], vec![5, 6, 21, 22, 4]),
            (6, vec![0], vec![24]),
            (6, vec![1, 1], vec![24, 25]),
            (6, vec![1, 0, 0, 0], vec![24, 25, 26, 28, 30]),
            (6, vec![1, 0, 0, 1], vec![24, 25, 26, 28, 29]),
            (6, vec![1, 0, 1, 1], vec![24, 25, 26, 27]),
            (6, vec![1, 0, 1, 0, 0], vec![24, 25, 26, 27, 28, 30]),
            (6, vec![1, 0, 1, 0, 1], vec![24, 25, 26, 27, 28, 29]),
            (7, vec![0], vec![31, 33]),
            (7, vec![1], vec![31, 32, 33]),
        ] {
            let mut stage = 0;
            let mut fact = 0;
            let mut facts = facts.into_iter();
            let mut actions = Vec::new();
            loop {
                let plan = unsafe { swr_v1_phpcoroutines_control(&mut stage, kind, fact, 0.0) };
                if plan.action == 0 {
                    break;
                }
                actions.push(plan.action);
                if matches!(plan.action, 5 | 6 | 24..=28 | 31) {
                    fact = facts.next().unwrap();
                }
                if matches!(plan.action, 4 | 16) {
                    break;
                }
            }
            assert_eq!(actions, expected);
            assert!(facts.next().is_none());
        }
    }
    #[test]
    fn request_creation_and_teardown_copied_fact_order() {
        for (kind, facts, expected) in [
            (8, vec![0, 7], vec![34, 39, 40]),
            (8, vec![0, 0], vec![34, 39, 4]),
            (8, vec![0, -1], vec![34, 39, 4]),
            (8, vec![1, 0, 7], vec![34, 35, 36, 39, 40]),
            (8, vec![1, 1, 0, 7], vec![34, 35, 36, 37, 39, 40]),
            (8, vec![1, 1, 1], vec![34, 35, 36, 37, 38, 4]),
            (9, vec![0], vec![41, 45]),
            (9, vec![1], vec![41, 42, 43, 44, 45]),
            (10, vec![0], vec![26, 48]),
            (10, vec![1], vec![26, 46, 47, 48]),
        ] {
            let mut stage = 0;
            let mut fact = 0;
            let mut facts = facts.into_iter();
            let mut actions = Vec::new();
            loop {
                let plan = unsafe { swr_v1_phpcoroutines_control(&mut stage, kind, fact, 0.0) };
                if plan.action == 0 {
                    break;
                }
                actions.push(plan.action);
                if matches!(plan.action, 26 | 34 | 36 | 37 | 39 | 41) {
                    fact = facts.next().unwrap();
                }
                if matches!(plan.action, 4 | 40 | 48) {
                    break;
                }
            }
            assert_eq!(actions, expected);
            assert!(facts.next().is_none());
        }
    }
    #[test]
    fn creation_fixed_prefix_is_exact_native_defined_window() {
        for (name, expected) in [
            (&b"__destruct"[..], 1),
            (&b"__destructor"[..], 1),
            (&b"__destruc\0"[..], 0),
            (&b"x_destruct"[..], 0),
        ] {
            assert_eq!(
                unsafe { swr_v1_phpcoroutines_create_destructor(name.as_ptr()) },
                expected
            );
        }
    }
}
