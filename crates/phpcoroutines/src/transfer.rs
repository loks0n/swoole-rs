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
    // ABI v1 keeps the parameter; no remaining kind depends on the stack limit.
    _stack_limit: u8,
) -> u32 {
    // SAFETY: per this function's `# Safety` contract, `stage` is live, aligned and exclusive.
    let stage = unsafe { &mut *stage };
    let (action, next) = step(*stage, kind, observation);
    *stage = next;
    action
}

/// Table steps cover stages below this; every transfer finishes before reaching it.
const STAGES: usize = 8;

/// One table step: the action, and the stage after it (`u8::MAX` once done).
#[repr(C)]
#[derive(Clone, Copy)]
pub struct Step {
    pub(crate) action: u8,
    pub(crate) next: u8,
}

impl Step {
    pub(crate) const DONE: Self = Self {
        action: 0,
        next: u8::MAX,
    };

    /// A table entry for `step`'s result; compilation fails if a sequence outgrows `stages`.
    pub(crate) const fn new(action: u32, next: u32, stages: usize) -> Self {
        assert!(action < 64, "actions fit six bits");
        if action == 0 {
            return Self::DONE;
        }
        assert!((next as usize) < stages, "a sequence outgrows its table");
        #[expect(clippy::cast_possible_truncation, reason = "both checked above")]
        Self {
            action: action as u8,
            next: next as u8,
        }
    }
}

/// [`step`] for every kind, stage and observation, indexed `(kind * 8 + stage) * 2 + observation`,
/// so native code steps with a load instead of a call. Built at compile time from the same `step`.
#[unsafe(export_name = "swr_v1_phpcoroutines_transfer_table")]
pub static TRANSFER_TABLE: [Step; 12 * STAGES * 2] = {
    let mut table = [Step::DONE; 12 * STAGES * 2];
    let mut index = 0;
    while index < table.len() {
        #[expect(
            clippy::cast_possible_truncation,
            reason = "kinds, stages and flags are below 16"
        )]
        let (kind, stage, observation) = (
            (index / (STAGES * 2)) as u32,
            (index / 2 % STAGES) as u32,
            (index % 2) as u8,
        );
        let (action, next) = step(stage, kind, observation);
        table[index] = Step::new(action, next, STAGES);
        index += 1;
    }
    table
};

/// One transfer step from `stage`: the action, and the stage after it (`u32::MAX` once done).
const fn step(mut stage: u32, kind: u32, observation: u8) -> (u32, u32) {
    loop {
        let current = stage;
        stage = current.saturating_add(1);
        let action = match kind {
            8 | 9 => match current {
                0 => 17,              // native fiber observer handoff
                1 => 18,              // save originating/current native context
                2 => 19,              // restore destination native context
                3 if kind == 9 => 20, // resumed clock update
                3 => {
                    stage = 5;
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
                    stage = 6;
                    21 // original interrupt handler presence after short circuit
                }
                4 => 31, // yield after defer returns
                5 => 21, // refresh original handler only after yield returns
                6 if observation != 0 => 22,
                _ => 0,
            },
            _ => 0,
        };
        if action == 0 {
            stage = u32::MAX;
        }
        return (action, stage);
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

    #[test]
    fn table_matches_step() {
        for kind in 0..12u32 {
            for stage in 0..8u32 {
                for observation in 0..2u8 {
                    let entry = TRANSFER_TABLE
                        [(kind as usize * STAGES + stage as usize) * 2 + usize::from(observation)];
                    let (action, next) = step(stage, kind, observation);
                    assert_eq!(u32::from(entry.action), action);
                    assert_eq!(u32::from(entry.next), if action == 0 { 255 } else { next });
                }
            }
        }
    }
}
