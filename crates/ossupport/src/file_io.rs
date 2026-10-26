//! File read/write-all sequencing. Native owns every syscall, byte and errno.
#[repr(C)]
#[derive(Default)]
pub struct FileIoState {
    pub completed: usize,
    phase: u32,
}

/// 0 return completed bytes, 1 perform native IO, 2 warn then return, MAX invalid.
/// # Safety
/// State is initially zero and exclusively writable. Preserve length and cursor
/// between calls. After action 1 pass the native signed result and transient-error
/// flag. Execute every effect after return; no native pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_file_io_next(
    state: *mut FileIoState,
    length: usize,
    result: i64,
    retry: bool,
) -> u32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return u32::MAX;
    };
    match state.phase {
        0 => (),
        1 if result > 0 => {
            // Native size_t += ssize_t uses unsigned arithmetic.
            state.completed = state.completed.wrapping_add(crate::size_t(result));
        }
        1 if result == 0 => {
            state.phase = 2;
            return 0;
        }
        1 if retry => (),
        1 => {
            state.phase = 2;
            return 2;
        }
        2 => return 0,
        _ => return u32::MAX,
    }
    if state.completed < length {
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
    fn empty_stops_without_io() {
        let mut s = FileIoState::default();
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 0, -1, true) }, 0);
        assert_eq!(s.completed, 0);
    }
    #[test]
    fn progress_retry_zero_and_warning_have_distinct_prefixes() {
        let mut s = FileIoState::default();
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 4, 0, false) }, 1);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 4, 2, false) }, 1);
        assert_eq!(s.completed, 2);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 4, -1, true) }, 1);
        assert_eq!(s.completed, 2);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 4, 0, true) }, 0);
        assert_eq!(s.completed, 2);
        let mut s = FileIoState::default();
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 1, 0, false) }, 1);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 1, -1, false) }, 2);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 1, 1, false) }, 0);
        assert_eq!(s.completed, 0);
    }
    #[test]
    fn exact_completion_avoids_an_extra_call() {
        let mut s = FileIoState::default();
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 3, 0, false) }, 1);
        assert_eq!(unsafe { swr_v1_os_file_io_next(&mut s, 3, 3, false) }, 0);
        assert_eq!(s.completed, 3);
    }
}
