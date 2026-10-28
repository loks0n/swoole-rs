//! Remaining HTTP-local dispatch/index decisions. Execution stays native.
use crate::proxy::Prefix;
use crate::{INVALID, OVERFLOW};
use std::{fmt::Write, mem::MaybeUninit, slice};

/// 1=WebSocket,2=HTTP2,0=protocol error. WebSocket takes precedence.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_transport_route(websocket_status: u32, http2: u32) -> i32 {
    if websocket_status >= 2 {
        1
    } else if http2 != 0 {
        2
    } else {
        0
    }
}
/// Native proxy construction populates credentials only when both exist.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_proxy_auth_enabled(
    user_length: usize,
    password_length: usize,
) -> i32 {
    i32::from(user_length != 0 && password_length != 0)
}
/// Format the unknown-status TLS fallback using native snprintf prefix rules.
/// # Safety
/// Output is writable for capacity bytes and disjoint from aligned written.
/// Capacity0 queries size; otherwise capacity includes the trailing NUL.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_unknown_status(
    code: i32,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() || capacity != 0 && output.is_null() {
        return INVALID;
    }
    if capacity > i32::MAX as usize {
        return OVERFLOW;
    }
    let buffer = if capacity == 0 {
        &mut []
    } else {
        // SAFETY: non-null when `capacity != 0` (checked above), `capacity <= i32::MAX`, writable.
        unsafe { slice::from_raw_parts_mut(output.cast::<MaybeUninit<u8>>(), capacity - 1) }
    };
    let mut sink = Prefix {
        output: buffer,
        length: 0,
    };
    if write!(sink, "{code} Unknown Status").is_err() {
        return OVERFLOW;
    }
    let count = if capacity == 0 {
        sink.length
    } else {
        sink.length.min(capacity - 1)
    };
    if capacity != 0 {
        // SAFETY: `count <= capacity - 1`, inside the writable output.
        unsafe { output.wrapping_add(count).write(0) };
    }
    // SAFETY: `written` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { written.write(count) };
    0
}
