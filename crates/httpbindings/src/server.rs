//! HTTP server callback routing. Cursor only; native code owns all effects/data.
use crate::Text;
use crate::request::{bytes, case_prefix};

#[derive(Clone, Copy)]
#[repr(u32)]
enum ReceivePhase {
    Start,
    AfterHttpProbe,
    AfterMessageProbe,
    AfterConnection,
    AfterParse,
    AfterBadClose,
    AfterNotice,
    AfterPopulate,
    AfterHandshakeProbe,
    AfterRequestProbe,
    AfterHandshakePublish,
    AfterPrepare,
    AfterBefore,
    AfterProcess,
    AfterDefault,
    AfterCleanup,
}
const RECEIVE_PHASES: [ReceivePhase; 16] = [
    ReceivePhase::Start,
    ReceivePhase::AfterHttpProbe,
    ReceivePhase::AfterMessageProbe,
    ReceivePhase::AfterConnection,
    ReceivePhase::AfterParse,
    ReceivePhase::AfterBadClose,
    ReceivePhase::AfterNotice,
    ReceivePhase::AfterPopulate,
    ReceivePhase::AfterHandshakeProbe,
    ReceivePhase::AfterRequestProbe,
    ReceivePhase::AfterHandshakePublish,
    ReceivePhase::AfterPrepare,
    ReceivePhase::AfterBefore,
    ReceivePhase::AfterProcess,
    ReceivePhase::AfterDefault,
    ReceivePhase::AfterCleanup,
];
#[derive(Clone, Copy)]
#[repr(i32)]
enum ReceiveAction {
    ProbeHttp = 1,
    ProbeMessage,
    CheckConnection,
    Raw,
    WebSocket,
    Http2,
    InitializeParse,
    BadSendClose,
    NoticeInvalid,
    NoticeIncomplete,
    PopulateHook,
    ProbeHandshakeCallback,
    ProbeRequestCallback,
    PublishHandshake,
    PrepareCallback,
    CallBefore,
    Process,
    Cleanup,
    DefaultHandshake,
    DefaultRequest,
    Done,
}
fn next(phase: &mut u32, to: ReceivePhase, action: ReceiveAction) -> i32 {
    *phase = to as u32;
    action as i32
}

/// Advance one callback-routing decision. Flags/result are freshly observed by
/// the preceding native action, not snapshots retained across effects.
/// # Safety
/// Phase points to one initialized, writable, caller-local cursor; it owns no
/// native object and must remain valid only for this call. Invalid phase returns-1.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_receive(
    phase: *mut u32,
    flags: u32,
    result: u32,
) -> i32 {
    // SAFETY: `phase` is null or aligned, writable and exclusively lent for this call.
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return -1;
    };
    let Some(&current) = RECEIVE_PHASES.get(*phase as usize) else {
        return -1;
    };
    use ReceiveAction as A;
    use ReceivePhase as P;
    match current {
        P::Start => {
            if flags & 1 != 0 {
                next(phase, P::AfterHttpProbe, A::ProbeHttp)
            } else if flags & 2 != 0 {
                next(phase, P::AfterMessageProbe, A::ProbeMessage)
            } else {
                A::Raw as i32
            }
        }
        P::AfterHttpProbe => {
            if result != 0 {
                next(phase, P::AfterConnection, A::CheckConnection)
            } else if flags & 2 != 0 {
                next(phase, P::AfterMessageProbe, A::ProbeMessage)
            } else {
                A::Raw as i32
            }
        }
        P::AfterMessageProbe => {
            if result != 0 {
                next(phase, P::AfterConnection, A::CheckConnection)
            } else {
                A::Raw as i32
            }
        }
        P::AfterConnection => {
            if flags & 1 != 0 {
                A::WebSocket as i32
            } else if flags & 2 != 0 {
                A::Http2 as i32
            } else {
                next(phase, P::AfterParse, A::InitializeParse)
            }
        }
        P::AfterParse => {
            if result != 0 {
                next(phase, P::AfterBadClose, A::BadSendClose)
            } else {
                next(phase, P::AfterPopulate, A::PopulateHook)
            }
        }
        P::AfterBadClose => next(
            phase,
            P::AfterNotice,
            if result != 0 {
                A::NoticeInvalid
            } else {
                A::NoticeIncomplete
            },
        ),
        P::AfterNotice | P::AfterProcess | P::AfterDefault => {
            next(phase, P::AfterCleanup, A::Cleanup)
        }
        P::AfterPopulate => {
            if result != 0 {
                next(phase, P::AfterHandshakeProbe, A::ProbeHandshakeCallback)
            } else {
                next(phase, P::AfterRequestProbe, A::ProbeRequestCallback)
            }
        }
        P::AfterHandshakeProbe => {
            if result != 0 {
                next(phase, P::AfterHandshakePublish, A::PublishHandshake)
            } else {
                next(phase, P::AfterDefault, A::DefaultHandshake)
            }
        }
        P::AfterRequestProbe => {
            if result != 0 {
                next(phase, P::AfterPrepare, A::PrepareCallback)
            } else {
                next(phase, P::AfterDefault, A::DefaultRequest)
            }
        }
        P::AfterHandshakePublish => next(phase, P::AfterPrepare, A::PrepareCallback),
        P::AfterPrepare => {
            if result != 0 {
                next(phase, P::AfterBefore, A::CallBefore)
            } else {
                next(phase, P::AfterProcess, A::Process)
            }
        }
        P::AfterBefore => {
            if result != 0 {
                next(phase, P::AfterProcess, A::Process)
            } else {
                A::Done as i32
            }
        }
        P::AfterCleanup => A::Done as i32,
    }
}

/// # Safety
/// Spans contain initialized readable bytes for the call. Native container order
/// and default callback identity remain authoritative; default entries are skipped
/// by the native custody guard before observing a potentially absent context path.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_handler(path: Text, pattern: Text) -> i32 {
    // SAFETY: `path` spans `length` initialized bytes (null only when empty) for this call.
    let path = unsafe { bytes(path) };
    // SAFETY: `pattern` spans `length` initialized bytes (null only when empty) for this call.
    let pattern = unsafe { bytes(pattern) };
    let (Some(path), Some(pattern)) = (path, pattern) else {
        return -1;
    };
    i32::from(case_prefix(path, pattern))
}

/// Native errno values are supplied by the actual platform, never guessed here.
#[repr(C)]
pub struct AcceptErrors {
    pub per_process: i32,
    pub system: i32,
    pub timeout: i32,
    pub bad_ssl: i32,
    pub canceled: i32,
}
/// # Safety
/// Errors points to initialized platform constants. Native callback creation and
/// socket effects have already returned. Result: retry/sleep/cancel/error=0/1/2/3.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_accept(
    has_connection: u32,
    cid: i64,
    error: i32,
    errors: *const AcceptErrors,
) -> i32 {
    // SAFETY: `errors` is null or aligned, initialized and lent for this call.
    let Some(errors) = (unsafe { errors.as_ref() }) else {
        return -1;
    };
    if has_connection != 0 {
        return if cid < 0 { 1 } else { 0 };
    }
    if error == errors.per_process || error == errors.system {
        1
    } else if error == errors.timeout || error == errors.bad_ssl {
        0
    } else if error == errors.canceled {
        2
    } else {
        3
    }
}
