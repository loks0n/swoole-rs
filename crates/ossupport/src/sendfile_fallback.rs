//! One-read/one-write fallback policy; native owns buffer, offset and IO.
#[repr(C)]
#[derive(Default)]
pub struct SendfileFallbackState {
    pub amount: usize,
    pub result: i64,
    phase: u32,
}
/// 0 done, 1 native pread, 2 native write, 3 warn pread and return,
/// 4 warn write and return, 5 native offset += result and return.
/// # Safety
/// Initially zero, exclusively writable stack cursor. Preserve size/capacity.
/// Supply the preceding native IO result; run each effect after Rust returns.
/// No buffer, offset pointer, errno, native call or borrow survives a return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_sendfile_fallback_next(
    state: *mut SendfileFallbackState,
    size: usize,
    capacity: usize,
    observed: i64,
) -> u32 {
    // SAFETY: `state` is null or the caller's aligned, exclusively owned state.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return u32::MAX;
    };
    match state.phase {
        0 => {
            state.amount = size.min(capacity);
            state.phase = 1;
            1
        }
        1 if observed > 0 => {
            state.amount = crate::size_t(observed);
            state.phase = 2;
            2
        }
        1 => {
            state.result = -1; // Pinned SW_ERR, including read EOF/zero.
            state.phase = 3;
            3
        }
        2 => {
            state.result = observed;
            state.phase = 3;
            if observed < 0 { 4 } else { 5 }
        }
        3 => 0,
        _ => u32::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn zero_size_still_requests_native_read_then_warns_on_zero() {
        let mut s = SendfileFallbackState::default();
        assert_eq!(
            unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 0, 64, 0) },
            1
        );
        assert_eq!(s.amount, 0);
        assert_eq!(
            unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 0, 64, 0) },
            3
        );
        assert_eq!(s.result, -1);
    }
    #[test]
    fn single_write_preserves_zero_partial_and_error_results() {
        for result in [-2, -1, 0, 1, 7] {
            let mut s = SendfileFallbackState::default();
            assert_eq!(
                unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 100, 64, 0) },
                1
            );
            assert_eq!(s.amount, 64);
            assert_eq!(
                unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 100, 64, 7) },
                2
            );
            assert_eq!(s.amount, 7);
            assert_eq!(
                unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 100, 64, result) },
                if result < 0 { 4 } else { 5 }
            );
            assert_eq!(s.result, result);
            assert_eq!(
                unsafe { swr_v1_os_sendfile_fallback_next(&mut s, 100, 64, 0) },
                0
            );
        }
    }
}
