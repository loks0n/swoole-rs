//! Common dispatch admission only; Native owns invocation, async and all effects.
#[repr(u32)]
enum Action {
    Done,
    ObserveCoroutine,
    Direct,
    Async,
}

/// Blocking admission deliberately skips the Native coroutine observation.
/// Every invocation/async/yield happens after Rust returns, with no retained
/// callback, context, std::function representation or borrowed Native payload.
/// # Safety
/// Phase is independent aligned exclusive scalar storage initialized to zero.
/// Observation is fresh only after ObserveCoroutine. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_async(
    phase: *mut u32,
    blocking: u8,
    coroutine: u8,
) -> u32 {
    // SAFETY: `phase` is null or the caller's aligned, exclusively owned phase storage.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Action::Done as u32;
    };
    let (action, next) = match *phase {
        0 if blocking != 0 => (Action::Direct, 2),
        0 => (Action::ObserveCoroutine, 1),
        1 if coroutine != 0 => (Action::Async, 2),
        1 => (Action::Direct, 2),
        _ => (Action::Done, 2),
    };
    *phase = next;
    action as u32
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn admission_short_circuits_and_consumes_only_requested_fact() {
        for observed in [0, 1] {
            let mut blocking = 0;
            assert_eq!(
                unsafe { swr_v1_phphelpers_async(&mut blocking, 1, observed) },
                2
            );
            assert_eq!(blocking, 2);
            let mut conditional = 0;
            assert_eq!(
                unsafe { swr_v1_phphelpers_async(&mut conditional, 0, 0) },
                1
            );
            assert_eq!(conditional, 1);
            assert_eq!(
                unsafe { swr_v1_phphelpers_async(&mut conditional, 0, observed) },
                if observed != 0 { 3 } else { 2 }
            );
            assert_eq!(
                unsafe { swr_v1_phphelpers_async(&mut conditional, 0, observed) },
                0
            );
        }
    }
}
