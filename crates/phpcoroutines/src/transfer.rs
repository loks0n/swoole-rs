//! Context transfer ordering. Zend storage and all effects remain native.
/// # Safety
/// Stage is exclusive writable POD initially zero. Kind/capability stay fixed
/// for the invocation; observation is the fresh requested native presence fact.
/// No context, VM page, output or serializer pointer enters Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_transfer(
    stage: *mut u32,
    kind: u32,
    observation: u8,
    stack_limit: u8,
) -> u32 {
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        let action = match kind {
            0 | 1 => match current {
                0 => 1, // native VM fields, in their original order
                1 => 2, // fresh in_silence
                2 if observation != 0 => 3,
                2 => continue,
                3 if stack_limit != 0 => 4,
                _ => 0,
            },
            2 | 3 => match current {
                0 => 5, // fresh output-handler count or saved-output presence
                1 if observation != 0 => 6,
                1 if kind == 2 => 7, // save clears output_ptr on empty output
                _ => 0,
            },
            4 | 5 => match current {
                0 => 8,
                1 if observation != 0 => 9,
                1 => continue,
                2 => 10,
                3 if observation != 0 => 11,
                3 => continue,
                4 => 12,
                5 if observation != 0 => 13,
                _ => 0,
            },
            6 | 7 => match current {
                0 => 14,
                1 => 15,
                2 => 16,
                _ => 0,
            },
            8 | 9 => match current {
                0 => 17,              // native fiber observer handoff
                1 => 18,              // save originating/current native context
                2 => 19,              // restore destination native context
                3 if kind == 9 => 20, // resumed clock update
                3 => {
                    *stage = 5;
                    21 // yield has no clock update
                }
                4 => 21, // fresh callback presence, after restore/clock
                5 if observation != 0 => 22,
                5 => continue,
                6 => 23, // native tracing after optional callback returns
                _ => 0,
            },
            10 => match current {
                0 => 24,                     // fresh Native Coroutine presence
                1 if observation != 0 => 25, // fresh completion state
                1 => 0,
                2 if observation == 0 => 23, // trace before resume
                2 => 0,
                3 => 26,
                _ => 0,
            },
            11 => match current {
                0 => 27, // fresh task presence
                1 if observation != 0 => 28,
                2 if observation != 0 => 29,
                3 if observation != 0 => 30,
                1..=3 => {
                    *stage = 6;
                    21 // original interrupt handler presence after short circuit
                }
                4 => 31, // yield after defer returns
                5 => 21, // refresh original handler only after yield returns
                6 if observation != 0 => 22,
                _ => 0,
            },
            12 | 13 => match current {
                0 => 1, // Native VM fields before metadata silence policy
                1 => 3,
                2 if stack_limit != 0 => 4,
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
    fn yield_resume_order_and_optional_callback() {
        for (kind, present, expected) in [
            (8, 0, vec![17, 18, 19, 21, 23]),
            (8, 1, vec![17, 18, 19, 21, 22, 23]),
            (9, 0, vec![17, 18, 19, 20, 21, 23]),
            (9, 1, vec![17, 18, 19, 20, 21, 22, 23]),
        ] {
            let mut stage = 0;
            let mut observation = 0;
            let mut actual = Vec::new();
            loop {
                let action =
                    unsafe { swr_v1_phpcoroutines_transfer(&mut stage, kind, observation, 0) };
                if action == 0 {
                    break;
                }
                actual.push(action);
                if action == 21 {
                    observation = present;
                }
            }
            assert_eq!(actual, expected);
        }
    }

    #[test]
    fn interrupt_short_circuit_and_fresh_handler_order() {
        for (kind, facts, expected) in [
            (10, vec![0], vec![24]),
            (10, vec![1, 1], vec![24, 25]),
            (10, vec![1, 0], vec![24, 25, 23, 26]),
            (11, vec![0, 0], vec![27, 21]),
            (11, vec![0, 1], vec![27, 21, 22]),
            (11, vec![1, 0, 1], vec![27, 28, 21, 22]),
            (11, vec![1, 1, 0, 1], vec![27, 28, 29, 21, 22]),
            (11, vec![1, 1, 1, 0], vec![27, 28, 29, 30, 31, 21]),
            (11, vec![1, 1, 1, 1], vec![27, 28, 29, 30, 31, 21, 22]),
        ] {
            let mut stage = 0;
            let mut observation = 0;
            let mut facts = facts.into_iter();
            let mut actual = Vec::new();
            loop {
                let action =
                    unsafe { swr_v1_phpcoroutines_transfer(&mut stage, kind, observation, 0) };
                if action == 0 {
                    break;
                }
                actual.push(action);
                if matches!(action, 21 | 24 | 25 | 27 | 28 | 29) {
                    observation = facts.next().unwrap();
                }
            }
            assert_eq!(actual, expected);
            assert!(facts.next().is_none());
        }
    }
}
