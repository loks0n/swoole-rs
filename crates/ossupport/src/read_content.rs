//! Complete read/grow loop sequence; native retains File/String and all effects.
#[repr(C)]
#[derive(Debug, Default)]
pub struct ReadContentState {
    pub phase: u32,
}
/// 1 native read; 2 native grow(result) THEN freshly observed read; 0 return.
/// Initial allocation occurs natively before the first call. Supply the last
/// signed read result after each read; no total, buffer or owner is retained.
/// # Safety
/// state is an exclusive zeroed live caller-stack state for this invocation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_read_content_next(
    state: *mut ReadContentState,
    result: i64,
) -> u32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return u32::MAX;
    };
    match state.phase {
        0 => {
            state.phase = 1;
            1
        }
        1 if result > 0 => 2,
        1 => {
            state.phase = 2;
            0
        }
        _ => u32::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_sequence_matches_original_read_grow_loop() {
        for a in [1, 3, 64] {
            for b in [1, 3, 64] {
                for last in [i64::MIN, -1, 0] {
                    let mut state = ReadContentState::default();
                    let actions = [i64::MIN, a, b, last]
                        .map(|n| unsafe { swr_v1_os_read_content_next(&mut state, n) });
                    assert_eq!(actions, [1, 2, 2, 0]);
                }
            }
        }
    }
    #[test]
    fn first_read_is_unconditional_and_nonpositive_never_grows_or_retries() {
        for n in [i64::MIN, -1, 0] {
            let mut state = ReadContentState::default();
            assert_eq!(unsafe { swr_v1_os_read_content_next(&mut state, n) }, 1);
            assert_eq!(unsafe { swr_v1_os_read_content_next(&mut state, n) }, 0);
            assert_eq!(
                unsafe { swr_v1_os_read_content_next(&mut state, 1) },
                u32::MAX
            );
        }
        assert_eq!(
            unsafe { swr_v1_os_read_content_next(std::ptr::null_mut(), 1) },
            u32::MAX
        );
        assert_eq!(std::mem::size_of::<ReadContentState>(), 4);
    }
}
