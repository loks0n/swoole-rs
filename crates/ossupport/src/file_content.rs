//! Lazy whole-file outcome sequencing; native owns every File/String effect.
#[repr(C)]
#[derive(Debug, Default)]
pub struct FileContentState {
    pub phase: u32,
    pub size: i64,
}
/// Exclusive zeroed caller-stack state. 0 return null, 1 stat, 2 observe maximum,
/// 3 warn open/null, 4 log empty/null, 5 log large/null, 6 allocate/read/finalize.
/// Supply ready only initially, signed size after action1, maximum after action2.
/// All native effects, including return/destruction, occur after this call.
/// # Safety
/// state points to an exclusive live state for this synchronous invocation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_file_content_next(
    state: *mut FileContentState,
    ready: bool,
    size: i64,
    maximum: u64,
) -> u32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return u32::MAX;
    };
    match state.phase {
        0 => {
            if ready {
                state.phase = 1;
                1
            } else {
                state.phase = 3;
                3
            }
        }
        1 => {
            if size <= 0 {
                state.phase = 3;
                if size == 0 { 4 } else { 0 }
            } else {
                state.size = size;
                state.phase = 2;
                2
            }
        }
        2 => {
            state.phase = 3;
            if crate::swr_v1_os_content(state.size.cast_unsigned(), maximum) == 2 {
                5
            } else {
                6
            }
        }
        _ => u32::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn actions(ready: bool, size: i64, maximum: u64) -> Vec<u32> {
        let mut state = FileContentState::default();
        let mut out = Vec::new();
        loop {
            let action = unsafe { swr_v1_os_file_content_next(&mut state, ready, size, maximum) };
            out.push(action);
            if action != 1 && action != 2 {
                break;
            }
        }
        out
    }
    #[test]
    fn matches_pinned_branch_order_with_lazy_observations() {
        for ready in [false, true] {
            for size in [i64::MIN, -1, 0, 1, 7, i64::MAX] {
                for maximum in [0, 1, 6, 7, u64::MAX] {
                    let expected = if !ready {
                        vec![3]
                    } else if size < 0 {
                        vec![1, 0]
                    } else if size == 0 {
                        vec![1, 4]
                    } else if size.cast_unsigned() > maximum {
                        vec![1, 2, 5]
                    } else {
                        vec![1, 2, 6]
                    };
                    assert_eq!(actions(ready, size, maximum), expected);
                }
            }
        }
    }
    #[test]
    fn only_requested_facts_are_observed() {
        let mut state = FileContentState::default();
        assert_eq!(
            unsafe { swr_v1_os_file_content_next(&mut state, true, i64::MIN, u64::MAX) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_os_file_content_next(&mut state, false, 7, u64::MAX) },
            2
        );
        assert_eq!(
            unsafe { swr_v1_os_file_content_next(&mut state, false, -99, 6) },
            5
        );
        assert_eq!(state.size, 7);
        assert_eq!(
            unsafe { swr_v1_os_file_content_next(&mut state, true, 1, 1) },
            u32::MAX
        );
        assert_eq!(
            unsafe { swr_v1_os_file_content_next(std::ptr::null_mut(), true, 1, 1) },
            u32::MAX
        );
        assert_eq!(std::mem::size_of::<FileContentState>(), 16);
    }
}
