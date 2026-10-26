#[repr(u32)]
enum Write {
    False = 0,
    True = 1,
    Descriptor = 2,
    Lookup = 3,
    Reactor = 4,
    Backend = 5,
    WarnEmpty = 6,
    WarnUnknown = 7,
    WarnMissing = 8,
}

/// Whole write admission/result policy after native arguments. Rust never reads
/// payload bytes or invokes IO; backend buffering and native lifetime stay native.
/// # Safety
/// Independent aligned phase0. Native supplies signed fd/backend result and
/// boolean presence observations, refreshing them after requested effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_write(
    phase: *mut u32,
    length: usize,
    observation: i64,
) -> u32 {
    use Write::*;
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 if length == 0 => (WarnEmpty, 99),
        0 => (Descriptor, 1),
        1 if observation < 0 => (WarnUnknown, 99),
        1 => (Lookup, 2),
        2 if observation == 0 => (WarnMissing, 99),
        2 => (Reactor, 3),
        3 => (Backend, 4),
        4 if observation >= 0 => (True, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}

#[repr(u32)]
enum Delete {
    False = 0,
    True = 1,
    Reactor = 2,
    Parse = 3,
    Descriptor = 4,
    Lookup = 5,
    Defer = 6,
    Backend = 7,
    Erase = 8,
    Invalidate = 9,
    Free = 10,
    WarnReady = 11,
    WarnUnknown = 12,
}

/// Delete routing preserves native effect order, including unconditional cleanup
/// after backend return. Retirement effects are native and separately unqualified.
/// # Safety
/// Independent aligned phase0. Native parser failure returns outside Rust;
/// observations are reactor/presence booleans, signed fd then backend status.
/// Backend observation is retained through metadata/invalidate/free effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_delete(phase: *mut u32, observation: i64) -> u32 {
    use Delete::*;
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 => (Reactor, 1),
        1 if observation == 0 => (WarnReady, 99),
        1 => (Parse, 2),
        2 => (Descriptor, 3),
        3 if observation < 0 => (WarnUnknown, 99),
        3 => (Lookup, 4),
        4 if observation == 0 => (False, 99),
        4 => (Defer, 5),
        5 => (Backend, 6),
        6 => (Erase, 7),
        7 => (Invalidate, 8),
        8 => (Free, 9),
        9 if observation == 0 => (True, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}

#[repr(u32)]
enum Cycle {
    False = 0,
    True = 1,
    Future = 2,
    Idle = 3,
    IsNull = 4,
    HasCallback = 5,
    HasData = 6,
    Defer = 7,
    Clear = 8,
    Create = 9,
    Assign = 10,
}

/// Cycle slot/null/replacement policy after native arguments/reactor check.
/// # Safety
/// Independent aligned phase0. Native supplies copied before/null/presence
/// booleans and owns all task slots, callable creation/deferral/destruction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_cycle(
    phase: *mut u32,
    before: u8,
    observation: u8,
) -> u32 {
    use Cycle::*;
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 if before != 0 => (Future, 1),
        0 => (Idle, 1),
        1 => (IsNull, 2),
        2 if observation != 0 => (HasCallback, 3),
        2 => (HasData, 4),
        3 if observation != 0 => (Defer, 5),
        4 if observation != 0 => (Defer, 6),
        4 | 6 => (Create, 7),
        5 => (Clear, 8),
        7 => (Assign, 9),
        8 | 9 => (True, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}
