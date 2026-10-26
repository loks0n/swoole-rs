//! Response packetization policy. Native Zend, buffer, codec and IO effects run
//! after each call returns; cursors contain no native pointer or ownership.
#[repr(i32)]
enum WriteAction {
    Http2 = 1,
    Buffer,
    Header,
    Read,
    Empty,
    Chunk,
    HeaderFailed,
}

/// Facts are observed by the caller at the current original decision point.
/// # Safety
/// `phase` is an initialized caller-owned writable scalar for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_write(phase: *mut u32, fact: u32) -> i32 {
    // SAFETY: `phase` is null or aligned, writable and exclusively lent for this call.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return -1;
    };
    let action = match *phase {
        0 if fact != 0 => WriteAction::Http2,
        0 => {
            *phase = 1;
            WriteAction::Buffer
        }
        1 if fact == 0 => {
            *phase = 2;
            WriteAction::Header
        }
        1 => {
            *phase = 3;
            WriteAction::Read
        }
        2 if fact == 0 => WriteAction::HeaderFailed,
        2 => {
            *phase = 3;
            WriteAction::Read
        }
        3 if fact == 0 => WriteAction::Empty,
        3 => WriteAction::Chunk,
        _ => return -1,
    };
    action as i32
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_cursor_does_not_select_a_native_effect() {
        for state in [14, u32::MAX] {
            let mut phase = state;
            assert_eq!(unsafe { swr_v1_httpbindings_write(&mut phase, 1) }, -1);
            assert_eq!(phase, state);
        }
        assert_eq!(
            unsafe { swr_v1_httpbindings_write(std::ptr::null_mut(), 1) },
            -1
        );
    }
}
