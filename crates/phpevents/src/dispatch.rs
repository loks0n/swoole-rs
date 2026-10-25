#[repr(u32)]
enum DispatchAction {
    Done = 0,
    Ok = 1,
    Error = 2,
    Warn = 3,
    ClearObject = 4,
    DeferObject = 5,
    DeleteEvent = 6,
    DeleteCallable = 7,
}

/// Callback result handling only. Native invocation has already completed before
/// phase0, so there is no Rust frame across PHP callback/GC/bailout/yield effects.
/// Modes readable0/writable1/defer2/cycle3; native owns every pointer and cleanup.
/// # Safety
/// Independent aligned phase0 storage. Mode and copied success remain constant.
/// All requested effects finish natively after return; lifetime paths are
/// separately qualified and never executed by the ordinary success-only model.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_dispatch(phase: *mut u32, mode: u32, success: u8) -> u32 {
    use DispatchAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    let (action, next) = match *phase {
        0 if success != 0 && mode <= 1 => (Ok, 99),
        0 if success != 0 && mode == 2 => (DeleteCallable, 5),
        0 if success != 0 && mode == 3 => (Done, 99),
        0 if mode <= 3 => (Warn, 1),
        1 if mode <= 1 => (ClearObject, 2),
        1 if mode == 2 => (DeleteCallable, 5),
        2 => (DeferObject, 3),
        3 => (DeleteEvent, 4),
        4 => (Error, 99),
        _ => (Done, 99),
    };
    *phase = next;
    action as u32
}
