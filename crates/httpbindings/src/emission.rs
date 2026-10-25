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

#[repr(i32)]
enum EndAction {
    Http2 = 20,
    WriteChunk,
    TrailerZero,
    ChunkZero,
    Trailer,
    ClearChunk,
    Prepare,
    Compression,
    Headers,
    Body,
    AppendAndSend,
    SendWhole,
    HeaderFailed,
    CloseFailed,
    Upgrade,
    Close,
    Done,
    Failed,
}

/// One native decision observation: HTTP2, chunked/data bits, write/send result,
/// trailer flag, nonempty/large payload, upgrade/socket predicate or keepalive.
/// No native field is speculatively read by Rust or retained between effects.
/// # Safety
/// `phase` is an initialized caller-owned writable scalar for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_end(phase: *mut u32, fact: u32) -> i32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return -1;
    };
    let action = match *phase {
        0 if fact != 0 => EndAction::Http2,
        0 => {
            *phase = 1;
            return 0;
        }
        1 if fact & 1 == 0 => {
            *phase = 6;
            EndAction::Prepare
        }
        1 if fact & 2 != 0 => {
            *phase = 2;
            EndAction::WriteChunk
        }
        1 => {
            *phase = 3;
            return 0;
        }
        2 if fact == 0 => EndAction::Failed,
        2 => {
            *phase = 3;
            return 0;
        }
        3 if fact != 0 => {
            *phase = 4;
            EndAction::TrailerZero
        }
        3 => {
            *phase = 5;
            EndAction::ChunkZero
        }
        4 if fact == 0 => EndAction::Failed,
        4 => {
            *phase = 10;
            EndAction::Trailer
        }
        5 if fact == 0 => EndAction::Failed,
        5 => {
            *phase = 10;
            EndAction::ClearChunk
        }
        6 if fact == 0 => {
            *phase = 9;
            EndAction::SendWhole
        }
        6 => {
            *phase = 7;
            EndAction::Compression
        }
        7 if fact != 0 => {
            *phase = 8;
            EndAction::Headers
        }
        7 => {
            *phase = 9;
            EndAction::AppendAndSend
        }
        8 if fact == 0 => EndAction::HeaderFailed,
        8 => {
            *phase = 11;
            EndAction::Body
        }
        9 | 11 if fact == 0 => EndAction::CloseFailed,
        9 | 11 => {
            *phase = 10;
            return 0;
        }
        10 if fact != 0 => {
            *phase = 12;
            EndAction::Upgrade
        }
        10 => {
            *phase = 12;
            return 0;
        }
        12 if fact == 0 => {
            *phase = 13;
            EndAction::Close
        }
        12 | 13 => EndAction::Done,
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
            assert_eq!(unsafe { swr_v1_httpbindings_end(&mut phase, 1) }, -1);
            assert_eq!(phase, state);
            assert_eq!(unsafe { swr_v1_httpbindings_write(&mut phase, 1) }, -1);
            assert_eq!(phase, state);
        }
        assert_eq!(
            unsafe { swr_v1_httpbindings_end(std::ptr::null_mut(), 1) },
            -1
        );
        assert_eq!(
            unsafe { swr_v1_httpbindings_write(std::ptr::null_mut(), 1) },
            -1
        );
    }
}
