#[repr(u32)]
enum StreamAction {
    Error = 0,
    Return = 1,
    ReadStream = 2,
    CastStream = 3,
    ReadFd = 4,
    ReadAsync = 5,
    ReadSocket = 6,
    ReadSocketFd = 7,
    SetAsync = 8,
    WarnResource = 9,
}

/// Extended stream conversion preserves native wrapper/descriptor effects and
/// the original optional PHP-socket fallback without filtering that socket fd.
/// # Safety
/// Independent aligned phase storage starts0. ReadFd supplies signed fd,
/// CastStream supplies Zend SUCCESS0; other observations are boolean. Native
/// owns streams, wrapper pointers, socket storage and the async output.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_stream(
    phase: *mut u32,
    resource: u8,
    sockets: u8,
    observation: i64,
) -> u32 {
    use StreamAction::{
        CastStream, Error, ReadAsync, ReadFd, ReadSocket, ReadSocketFd, ReadStream, Return,
        SetAsync, WarnResource,
    };
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Error as u32;
    };
    let (action, next) = match *phase {
        0 if resource != 0 => (ReadStream, 1),
        1 if observation != 0 => (CastStream, 2),
        1 if sockets != 0 => (ReadSocket, 5),
        2 if observation == 0 => (ReadFd, 3),
        3 if observation >= 0 => (ReadAsync, 4),
        4 => (Return, 99),
        5 if observation != 0 => (ReadSocketFd, 6),
        6 => (SetAsync, 4),
        0..=3 | 5 => (WarnResource, 99),
        _ => (Error, 99),
    };
    *phase = next;
    action as u32
}
