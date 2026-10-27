//! Coroutine HTTP server handler routing and accept policy. Native code owns all effects/data.
use crate::Text;
use crate::request::{bytes, case_prefix};

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
        return i32::from(cid < 0);
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
