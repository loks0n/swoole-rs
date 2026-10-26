#[repr(u32)]
enum UpdateAction {
    False = 0,
    True = 1,
    CreateRead = 2,
    CreateWrite = 3,
    NewRead = 4,
    OldRead = 5,
    DeferRead = 6,
    AssignRead = 7,
    NewWrite = 8,
    OldWrite = 9,
    DeferWrite = 10,
    AssignWrite = 11,
    ValidateRead = 12,
    ValidateWrite = 13,
    BackendSet = 14,
    WarnRead = 15,
    WarnWrite = 16,
    WarnSet = 17,
}

fn validate(events: i64) -> (UpdateAction, u32) {
    if events & 512 != 0 {
        (UpdateAction::ValidateRead, 11)
    } else if events & 1024 != 0 {
        (UpdateAction::ValidateWrite, 12)
    } else {
        (UpdateAction::BackendSet, 13)
    }
}

/// Callback replacement and mask validation after native reactor/argument/fd/
/// registry checks. Legacy copied-observation protocol. Selected owned callers internalize
/// persistent identity checks and publication; Native constructs/defers payloads.
/// # Safety
/// Phase points to independent aligned storage initially0. Each requested
/// boolean observation is refreshed after native effects; backend result signed.
/// Native payload lifetime and callbacks remain outside Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_update(
    phase: *mut u32,
    events: i64,
    observation: i64,
) -> u32 {
    use UpdateAction::*;
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 => (CreateRead, 1),
        1 => (CreateWrite, 2),
        2 => (NewRead, 3),
        3 if observation != 0 => (OldRead, 4),
        3 => (NewWrite, 7),
        4 if observation != 0 => (DeferRead, 5),
        4 | 5 => (AssignRead, 6),
        6 => (NewWrite, 7),
        7 if observation != 0 => (OldWrite, 8),
        7 => validate(events),
        8 if observation != 0 => (DeferWrite, 9),
        8 | 9 => (AssignWrite, 10),
        10 => validate(events),
        11 if observation == 0 => (WarnRead, 99),
        11 if events & 1024 != 0 => (ValidateWrite, 12),
        11 => (BackendSet, 13),
        12 if observation == 0 => (WarnWrite, 99),
        12 => (BackendSet, 13),
        13 if observation < 0 => (WarnSet, 99),
        13 => (True, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}
