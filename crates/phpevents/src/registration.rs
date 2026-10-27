const READ: i64 = 1 << 9;
const WRITE: i64 = 1 << 10;

#[repr(u32)]
enum AddAction {
    False = 0,
    ReturnFd = 1,
    CheckDuplicate = 2,
    CreateRead = 3,
    CreateWrite = 4,
    Allocate = 5,
    BackendAdd = 6,
    Publish = 7,
    WarnUnknown = 8,
    WarnFd = 9,
    WarnDuplicate = 10,
    WarnEvents = 11,
    WarnRead = 12,
    WarnWrite = 13,
    DeleteRead = 14,
    WarnAdd = 15,
    FreeSocket = 16,
    FreeObject = 17,
}

/// Complete ordinary add admission/publication/cleanup ordering. Native reactor
/// check and descriptor conversion precede phase0. Duplicate lookup and callback
/// creation stay lazy; registration/map ownership remains native.
/// # Safety
/// Independent aligned phase0 storage. Native effects run after return. Fresh
/// booleans follow duplicate/callback requests; backend result is signed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_add(
    phase: *mut u32,
    fd: i32,
    events: i64,
    observation: i64,
) -> u32 {
    use AddAction::{
        Allocate, BackendAdd, CheckDuplicate, CreateRead, CreateWrite, DeleteRead, False,
        FreeObject, FreeSocket, Publish, ReturnFd, WarnAdd, WarnDuplicate, WarnEvents, WarnFd,
        WarnRead, WarnUnknown, WarnWrite,
    };
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 if fd < 0 => (WarnUnknown, 99),
        0 if fd == 0 && events & WRITE != 0 => (WarnFd, 99),
        0 => (CheckDuplicate, 1),
        1 if observation != 0 => (WarnDuplicate, 99),
        1 if events & (READ | WRITE) == 0 => (WarnEvents, 99),
        1 => (CreateRead, 2),
        2 if events & READ != 0 && observation == 0 => (WarnRead, 99),
        2 => (CreateWrite, 3),
        3 if events & WRITE != 0 && observation == 0 => (WarnWrite, 4),
        3 => (Allocate, 5),
        4 => (DeleteRead, 99),
        5 => (BackendAdd, 6),
        6 if observation < 0 => (WarnAdd, 7),
        6 => (Publish, 8),
        7 => (FreeSocket, 10),
        8 => (ReturnFd, 99),
        10 => (FreeObject, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}
