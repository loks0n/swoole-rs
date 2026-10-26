//! Outer entropy progress only. Native retains getrandom/backend and bytes.
#[repr(C)]
#[derive(Default)]
pub struct RandomBytesState {
    pub completed: usize,
    phase: u32,
}
/// 0 return completed, 1 native getrandom, MAX invalid. Zero results repeat.
/// # Safety
/// Exclusive initially-zero stack cursor; keep size fixed. After action 1 pass
/// its signed result and native errno transient flag (only meaningful for -1).
/// Execute IO after return. Rust never receives a destination or backend pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_random_bytes_next(
    state: *mut RandomBytesState,
    size: usize,
    result: i64,
    retry: bool,
) -> u32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return u32::MAX;
    };
    match state.phase {
        0 => (),
        1 if result == -1 && !retry => {
            state.phase = 2;
            return 0;
        }
        1 if result == -1 => (),
        1 => state.completed = state.completed.wrapping_add(crate::size_t(result)),
        2 => return 0,
        _ => return u32::MAX,
    }
    if state.completed < size {
        state.phase = 1;
        1
    } else {
        state.phase = 2;
        0
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_size_has_no_native_call() {
        let mut s = RandomBytesState::default();
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 0, -1, true) },
            0
        );
        assert_eq!(s.completed, 0);
    }
    #[test]
    fn zero_and_transient_repeat_but_fatal_returns_partial_progress() {
        let mut s = RandomBytesState::default();
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 7, 0, false) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 7, 3, false) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 7, 0, false) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 7, -1, true) },
            1
        );
        assert_eq!(s.completed, 3);
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 7, -1, false) },
            0
        );
        assert_eq!(s.completed, 3);
    }
    #[test]
    fn exact_completion_does_not_request_more_entropy() {
        let mut s = RandomBytesState::default();
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 4, 0, false) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_os_random_bytes_next(&mut s, 4, 4, true) },
            0
        );
        assert_eq!(s.completed, 4);
    }
}
