/// Returned native effect tags. Zend kinds and pointers never enter this plan.
#[repr(u32)]
enum FdAction {
    Error = 0,
    Return = 1,
    Stream = 2,
    CastStream = 3,
    ReadFd = 4,
    ReadLong = 5,
    CheckCoSocket = 6,
    CoSocketProperty = 7,
    CheckClient = 8,
    ClientProperty = 9,
    CheckProcess = 10,
    ProcessProperty = 11,
    CheckPhpSocket = 12,
    ReadSocket = 13,
    CheckSocketClosed = 14,
    SocketFd = 15,
    CheckPropertyPresent = 16,
    CheckPropertyLong = 17,
    PropertyFd = 18,
    WarnResource = 19,
    WarnNegative = 20,
    WarnClosed = 21,
    WarnUnknown = 22,
}

/// Phase0; kinds resource0/long1/object2/other3, sockets support0/1.
/// Each returned effect finishes natively before the next copied observation.
/// Only ReadLong/ReadFd observations are signed descriptors; CastStream is the
/// native Zend result (SUCCESS0); all other observations are boolean facts.
/// # Safety
/// Phase points to independent aligned u32 storage initialized to0. Native owns
/// pointers/values/streams and refreshes observations after each requested effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_fd(
    phase: *mut u32,
    kind: u32,
    sockets: u8,
    observation: i64,
) -> u32 {
    use FdAction::*;
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Error as u32;
    };
    let (action, next) = match *phase {
        0 => match kind {
            0 => (Stream, 1),
            1 => (ReadLong, 4),
            2 => (CheckCoSocket, 5),
            _ => (WarnUnknown, 99),
        },
        1 if observation != 0 => (CastStream, 2),
        1 => (WarnResource, 99),
        2 if observation == 0 => (ReadFd, 3),
        2 => (WarnResource, 99),
        3 if observation >= 0 => (Return, 99),
        3 => (WarnResource, 99),
        4 if observation >= 0 => (Return, 99),
        4 => (WarnNegative, 99),
        5 if observation != 0 => (CoSocketProperty, 9),
        5 => (CheckClient, 6),
        6 if observation != 0 => (ClientProperty, 9),
        6 => (CheckProcess, 7),
        7 if observation != 0 => (ProcessProperty, 9),
        7 if sockets != 0 => (CheckPhpSocket, 8),
        7 => (CheckPropertyPresent, 10),
        8 if observation != 0 => (ReadSocket, 11),
        8 => (CheckPropertyPresent, 10),
        9 => (CheckPropertyPresent, 10),
        10 if observation != 0 => (CheckPropertyLong, 12),
        10 => (Error, 99),
        11 => (CheckSocketClosed, 13),
        12 if observation != 0 => (PropertyFd, 14),
        12 => (Error, 99),
        13 if observation != 0 => (WarnClosed, 99),
        13 => (SocketFd, 14),
        // Object property/socket descriptors retain the original unfiltered
        // return semantics; do not impose the scalar-long nonnegative rule.
        14 => (Return, 99),
        _ => (Error, 99),
    };
    *phase = next;
    action as u32
}
