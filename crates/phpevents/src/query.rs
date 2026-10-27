#[repr(u32)]
enum QueryAction {
    False = 0,
    True = 1,
    Reactor = 2,
    Parse = 3,
    Descriptor = 4,
    Lookup = 5,
    Removed = 6,
    Events = 7,
    WarnUnknown = 8,
}

/// Whole isset frontend routing. Each native observation is lazy: no parser
/// without reactor, no registry lookup after failed conversion, no Socket field
/// access before presence and no mask read after a removed Socket.
/// # Safety
/// Independent aligned phase0 storage; native refreshes requested boolean/fd/
/// mask observations. Native owns all values, registry handle and Socket fields.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_query(
    phase: *mut u32,
    events: i64,
    observation: i64,
) -> u32 {
    use QueryAction::{
        Descriptor, Events, False, Lookup, Parse, Reactor, Removed, True, WarnUnknown,
    };
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase word.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 => (Reactor, 1),
        1 if observation != 0 => (Parse, 2),
        2 => (Descriptor, 3),
        3 if observation < 0 => (WarnUnknown, 99),
        3 => (Lookup, 4),
        4 if observation != 0 => (Removed, 5),
        5 if observation == 0 => (Events, 6),
        6 if observation & events != 0 => (True, 99),
        _ => (False, 99),
    };
    *phase = next;
    action as u32
}
