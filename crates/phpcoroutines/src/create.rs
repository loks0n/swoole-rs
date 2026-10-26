//! Coroutine creation admission. Request native facts only in original order.
/// # Safety
/// `phase` is exclusive writable POD initially zeroed. Native effects run only
/// after return; scalar observations describe the preceding requested fact.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_create(
    phase: *mut u32,
    observation: u64,
    maximum: u64,
    user_function: u8,
    internal_function: u8,
) -> u32 {
    // SAFETY: per this function's `# Safety` contract, `phase` is live, aligned and exclusive.
    let phase = unsafe { &mut *phase };
    match *phase {
        0 => {
            if observation >= maximum {
                return 1;
            }
            *phase = 1;
            2
        }
        1 => {
            if observation == 0 {
                return 3;
            }
            *phase = 2;
            4
        }
        2 => {
            if observation != u64::from(user_function)
                && observation != u64::from(internal_function)
            {
                return 5;
            }
            *phase = 3;
            6
        }
        3 => {
            *phase = 4;
            if observation == 0 { 7 } else { 8 }
        }
        _ => 8,
    }
}

/// Sole repeat-loop metadata for the existing Native kernel test frontend.
#[repr(C)]
pub struct RepeatState {
    count: i64,
    index: i64,
    pending: u8,
}
/// # Safety
/// State is exclusive live POD initialized with Native count, zero index/pending.
/// Call only initially or after the preceding Native sleep returns. The original
/// loop increments AFTER the effect; no Rust borrow/frame spans sleep/yield.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_repeat(state: *mut RepeatState) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    if state.pending != 0 {
        // Prior admission proves index < count <= i64::MAX, so this cannot overflow.
        state.index += 1;
        state.pending = 0;
    }
    if state.index < state.count {
        state.pending = 1;
        1
    } else {
        0
    }
}

#[cfg(test)]
mod repeat_tests {
    use super::*;
    #[test]
    fn native_signed_count_and_post_effect_increment() {
        for count in [-10, -1, 0, 1, 5, 1024] {
            let mut state = RepeatState {
                count,
                index: 0,
                pending: 0,
            };
            let mut effects = 0;
            unsafe {
                while swr_v1_phpcoroutines_repeat(&mut state) != 0 {
                    assert_eq!(state.index, effects);
                    effects += 1; // inert observation, no real sleep/coroutine
                }
            }
            assert_eq!(effects, count.max(0));
        }
        let mut state = RepeatState {
            count: i64::MAX,
            index: i64::MAX - 1,
            pending: 0,
        };
        unsafe {
            assert_eq!(swr_v1_phpcoroutines_repeat(&mut state), 1);
            assert_eq!(state.index, i64::MAX - 1);
            assert_eq!(swr_v1_phpcoroutines_repeat(&mut state), 0);
            assert_eq!(state.index, i64::MAX);
        }
    }
}
