//! File response range validation and packetization; native stat/MIME/IO remain effects.
#[repr(i32)]
enum FileAction {
    Http2 = 40,
    ReadHeaders,
    Mime,
    Header,
    Send,
    HeaderFailed,
    CloseFailed,
    MarkEnd,
    CloseDone,
    Done,
}

/// Preserve all defined signed native range comparisons. Rejected subtraction
/// overflow has no defined native reference result; never perform it in Rust.
/// # Safety
/// `resolved` is initialized writable caller storage for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_file_range(
    size: i64,
    offset: i64,
    length: i64,
    resolved: *mut i64,
) -> i32 {
    let Some(resolved) = (unsafe { resolved.as_mut() }) else {
        return -1;
    };
    if size < offset {
        return 1;
    }
    let Some(remaining) = size.checked_sub(offset) else {
        return 3;
    };
    if length > remaining {
        return 2;
    }
    *resolved = if length == 0 { remaining } else { length };
    0
}

/// One current native observation: HTTP2, MIME presence, header sent, send result,
/// nonempty file length or keepalive. The cursor holds no native pointer.
/// # Safety
/// `phase` is initialized writable caller storage for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_file(phase: *mut u32, fact: u32) -> i32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return -1;
    };
    let action = match *phase {
        0 if fact != 0 => FileAction::Http2,
        0 => {
            *phase = 1;
            FileAction::ReadHeaders
        }
        1 if fact == 0 => {
            *phase = 2;
            FileAction::Mime
        }
        1 => {
            *phase = 2;
            return 0;
        }
        2 if fact == 0 => {
            *phase = 3;
            FileAction::Header
        }
        2 => {
            *phase = 4;
            return 0;
        }
        3 if fact == 0 => FileAction::HeaderFailed,
        3 => {
            *phase = 4;
            return 0;
        }
        4 if fact != 0 => {
            *phase = 5;
            FileAction::Send
        }
        4 => {
            *phase = 6;
            FileAction::MarkEnd
        }
        5 if fact == 0 => FileAction::CloseFailed,
        5 => {
            *phase = 6;
            FileAction::MarkEnd
        }
        6 if fact == 0 => FileAction::CloseDone,
        6 => FileAction::Done,
        _ => return -1,
    };
    action as i32
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_ranges_and_cursors_do_not_publish_a_result() {
        let mut value = 91;
        assert_eq!(
            unsafe { swr_v1_httpbindings_file_range(i64::MAX, i64::MIN, 0, &mut value) },
            3
        );
        assert_eq!(value, 91);
        assert_eq!(
            unsafe { swr_v1_httpbindings_file_range(0, 0, 0, std::ptr::null_mut()) },
            -1
        );
        let mut phase = u32::MAX;
        assert_eq!(unsafe { swr_v1_httpbindings_file(&mut phase, 1) }, -1);
        assert_eq!(phase, u32::MAX);
    }
}
