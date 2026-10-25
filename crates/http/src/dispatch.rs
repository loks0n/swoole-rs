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
/// Phase0 receives configured-index1/directory2; phase1 receives scanOK4;
/// phase2 receives found-index8/autoindex16; phase3 receives filenameOK32.
/// Actions0=reject,1=accept,2=scan directory,3=native intersection,4=set filename.
/// # Safety
/// Phase is initialized/aligned/exclusively writable; native effects run only
/// after return. No Rust borrow, callback or owner survives those effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_index_file(phase: *mut u32, facts: u32) -> i32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return INVALID;
    };
    match *phase {
        0 if facts & 3 == 3 => {
            *phase = 1;
            2
        }
        0 => 1,
        1 if facts & 4 != 0 => {
            *phase = 2;
            3
        }
        1 => 0,
        2 if facts & 8 != 0 => {
            *phase = 3;
            4
        }
        2 => i32::from(facts & 16 != 0),
        3 => i32::from(facts & 32 != 0),
        _ => INVALID,
    }
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
        unsafe { output.add(count).write(0) };
    }
    unsafe { written.write(count) };
    0
}
