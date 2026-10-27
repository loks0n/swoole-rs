//! Whole remaining Scheduler control; Native Zend/resolver/Callable effects only.
#[repr(C)]
pub struct SchedulerConstants {
    pub success: i64,
    pub false_tag: i64,
    pub php_resolver: i64,
}

/// # Safety
/// Stage is local exclusive zeroed POD, kind/constants fixed. Observation is the
/// requested fresh Native scalar fact. No Callable, resolver, `HashTable`, zval,
/// reactor or callback pointer enters Rust. Native effects run after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_control(
    stage: *mut u32,
    kind: u32,
    observation: i64,
    constants: *const SchedulerConstants,
) -> u32 {
    // SAFETY: per this function's `# Safety` contract, `stage` is live, aligned and exclusive.
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        let action = match kind {
            0 => match current {
                0 => 1, // original Native call, following assert/null seed
                // SAFETY: per this function's `# Safety` contract, `constants` is live, aligned and initialized.
                1 if observation != unsafe { (*constants).success } => 2,
                1 => continue,
                2 => 3, // fresh exception after callback/error handler returns
                3 if observation != 0 => 4,
                3 => continue,
                4 => 5, // fresh result type only after exception effect returns
                // SAFETY: per this function's `# Safety` contract, `constants` is live, aligned and initialized.
                5 if observation == unsafe { (*constants).false_tag } => 7,
                5 => 6,
                _ => 0,
            },
            1 => match current {
                // SAFETY: per this function's `# Safety` contract, `constants` is live, aligned and initialized.
                0 if observation == unsafe { (*constants).php_resolver } => 8,
                0 => 10,
                1 => 9,
                2 => 11,
                _ => 0,
            },
            2 => match current {
                0 => 12, // resolver traversal before cache observation
                1 => 13,
                2 if observation != 0 => 14,
                2 => 0,
                3 => 15,
                _ => 0,
            },
            3 => match current {
                0 => 16,
                1 if observation != 0 => 17,
                _ => 0,
            },
            _ => 0,
        };
        if action == 0 {
            *stage = u32::MAX;
        }
        return action;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fresh_callback_error_exception_result_facts() {
        let constants = SchedulerConstants {
            success: -3,
            false_tag: 19,
            php_resolver: 71,
        };
        for (success, exception, result, expected) in [
            (-3, 0, 19, vec![1, 3, 5, 7]),
            (-3, 1, 0, vec![1, 3, 4, 5, 6]),
            (0, 1, 19, vec![1, 2, 3, 4, 5, 7]),
            (0, 0, 7, vec![1, 2, 3, 5, 6]),
        ] {
            let mut stage = 0;
            let mut observation = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe {
                    swr_v1_phpcoroutines_scheduler_control(
                        &raw mut stage,
                        0,
                        observation,
                        &raw const constants,
                    )
                };
                if action == 0 {
                    break;
                }
                actions.push(action);
                observation = match action {
                    1 => success,
                    3 => exception,
                    5 => result,
                    _ => observation,
                };
                if action == 6 || action == 7 {
                    break;
                }
            }
            assert_eq!(actions, expected);
        }
    }
    #[test]
    fn resolver_and_cleanup_queries_use_only_required_facts() {
        let constants = SchedulerConstants {
            success: 0,
            false_tag: 0,
            php_resolver: 71,
        };
        for (kind, observation, expected) in [
            (1, 71, vec![8, 9, 11]),
            (1, 99, vec![10]),
            (2, 0, vec![12, 13]),
            (2, 1, vec![12, 13, 14, 15]),
            (3, 0, vec![16]),
            (3, 1, vec![16, 17]),
        ] {
            let mut stage = 0;
            let mut actions = Vec::new();
            loop {
                let action = unsafe {
                    swr_v1_phpcoroutines_scheduler_control(
                        &raw mut stage,
                        kind,
                        observation,
                        &raw const constants,
                    )
                };
                if action == 0 {
                    break;
                }
                actions.push(action);
                if action == 10 || action == 11 {
                    break;
                }
            }
            assert_eq!(actions, expected);
        }
        // Cache/options operations never dereference unused resolver/tag facts.
        let mut stage = 0;
        assert_eq!(
            unsafe {
                swr_v1_phpcoroutines_scheduler_control(&raw mut stage, 3, 0, std::ptr::null())
            },
            16
        );
    }
}
