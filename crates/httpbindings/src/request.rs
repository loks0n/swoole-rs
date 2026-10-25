//! Header and URL decisions for the existing native PHP request callbacks.
use crate::Text;
use core::ffi::{c_char, c_int};

unsafe extern "C" {
    fn strncasecmp(left: *const c_char, right: *const c_char, count: usize) -> c_int;
    fn isspace(value: c_int) -> c_int;
}

pub(crate) fn case_equal(left: &[u8], right: &[u8]) -> bool {
    left.len() == right.len() && case_prefix(left, right)
}
pub(crate) fn case_prefix(left: &[u8], right: &[u8]) -> bool {
    left.len() >= right.len()
        && (right.is_empty()
            || unsafe {
                strncasecmp(left.as_ptr().cast(), right.as_ptr().cast(), right.len()) == 0
            })
}
pub(crate) unsafe fn bytes<'a>(text: Text) -> Option<&'a [u8]> {
    if text.length > isize::MAX as usize || (text.data.is_null() && text.length != 0) {
        return None;
    }
    if text.length == 0 {
        Some(&[])
    } else {
        Some(unsafe { core::slice::from_raw_parts(text.data, text.length) })
    }
}

/// # Safety
/// Both spans contain initialized readable bytes for this call; invalid spans
/// return-1. Method is the pinned llhttp method number; flags: cookie/compression.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_request_header(
    name: Text,
    value: Text,
    method: u32,
    flags: u32,
) -> i32 {
    let (Some(name), Some(value)) = (unsafe { bytes(name) }, unsafe { bytes(value) }) else {
        return -1;
    };
    if flags & 1 != 0 && case_equal(name, b"cookie") {
        return 1;
    }
    if case_equal(name, b"upgrade") {
        return 2;
    }
    if matches!(method, 0 | 3 | 4 | 28) && case_equal(name, b"content-type") {
        if case_prefix(value, b"application/x-www-form-urlencoded") {
            return 3;
        }
        if case_prefix(value, b"multipart/form-data") {
            return 4;
        }
    } else if flags & 2 != 0 && case_equal(name, b"accept-encoding") {
        return 5;
    } else if case_equal(name, b"transfer-encoding") && case_prefix(value, b"chunked") {
        return 6;
    }
    0
}

/// # Safety
/// Name is an initialized readable span. The return is a native known-key index;
/// 8 denotes the original unknown-name merge path. Invalid input returns-1.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_request_key(name: Text) -> i32 {
    const KEYS: [&[u8]; 8] = [
        b"host",
        b"user-agent",
        b"accept",
        b"content-type",
        b"content-length",
        b"authorization",
        b"connection",
        b"accept-encoding",
    ];
    let Some(name) = (unsafe { bytes(name) }) else {
        return -1;
    };
    KEYS.iter()
        .position(|key| case_equal(name, key))
        .unwrap_or(KEYS.len()) as i32
}

/// Native first calls mode0 on the original span, preserving its no-copy fast
/// path. A return2 requests native scratch copy+terminator before mode1; mode1
/// mutates that scratch exactly like strtok_r and the original trim helpers.
/// # Safety
/// Read spans are initialized; mode1 additionally requires writable data with a
/// terminator at data[length]. Value is readable through its native C-string terminator on scan paths, or for the bounded comparison on fast paths. fast_extent preserves the native pointer-size expression.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_tokens(
    data: *mut u8,
    length: usize,
    value: *const u8,
    fast_extent: usize,
    mode: u32,
) -> i32 {
    let Some(input) = (unsafe { bytes(Text { data, length }) }) else {
        return -1;
    };
    if mode == 0 {
        if length == 0 {
            return 0;
        }
        if length != fast_extent {
            return 2;
        }
        if value.is_null() {
            return -1;
        }
        // SW_STRCASEEQ uses sizeof(value)-1 on a pointer in the pinned helper.
        // Preserve its architecture-dependent bounded comparison, not strlen.
        return if unsafe { strncasecmp(data.cast(), value.cast(), length) } == 0 {
            1
        } else {
            2
        };
    }
    if mode != 1 {
        return -1;
    }
    if length == 0 {
        return 0;
    }
    let end = input.iter().position(|&c| c == 0).unwrap_or(length);
    // Raw byte effects permit the original value pointer to alias scratch.
    // Immutable token/value views exist only during the final pure comparison.
    let read = |index: usize| unsafe { data.add(index).read() };
    let write = |index: usize, byte| unsafe { data.add(index).write(byte) };
    let mut cursor = 0;
    while cursor < end {
        while cursor < end && read(cursor) == b',' {
            cursor += 1;
        }
        if cursor == end {
            break;
        }
        let start = cursor;
        while cursor < end && read(cursor) != b',' {
            cursor += 1;
        }
        let stop = cursor;
        if cursor < end {
            write(cursor, 0);
            cursor += 1;
        }
        let mut first = start;
        let mut last = stop;
        while first < last && unsafe { isspace((read(first) as c_char) as c_int) } != 0 {
            first += 1;
        }
        while last > first && unsafe { isspace((read(last - 1) as c_char) as c_int) } != 0 {
            last -= 1;
            write(last, 0);
        }
        if value.is_null() {
            return -1;
        }
        let value = unsafe { core::ffi::CStr::from_ptr(value.cast()) }.to_bytes();
        let token = unsafe { core::slice::from_raw_parts(data.add(first), last - first) };
        if case_equal(token, value) {
            return 1;
        }
    }
    0
}

#[repr(C)]
#[derive(Default)]
pub struct UrlParts {
    pub path_length: usize,
    pub query_offset: usize,
    pub query_length: usize,
}

/// # Safety
/// Input contains initialized bytes and output is a disjoint writable object.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_request_url(
    input: Text,
    output: *mut UrlParts,
) -> i32 {
    let (Some(input), Some(output)) = (unsafe { bytes(input) }, unsafe { output.as_mut() }) else {
        return -1;
    };
    let path_length = input.iter().position(|&c| c == b'?').unwrap_or(input.len());
    let query_offset = if path_length < input.len() {
        path_length + 1
    } else {
        input.len()
    };
    *output = UrlParts {
        path_length,
        query_offset,
        query_length: input.len() - query_offset,
    };
    0
}

#[repr(C)]
#[derive(Default)]
pub struct Trimmed {
    pub offset: usize,
    pub length: usize,
}

/// # Safety
/// Data is initialized/writable for length bytes and output is disjoint. The
/// original shrinking left-loop bound is intentional; this is not trim_matches.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_trim_quotes(
    data: *mut u8,
    length: usize,
    output: *mut Trimmed,
) -> i32 {
    if length > isize::MAX as usize || (data.is_null() && length != 0) {
        return -1;
    }
    let Some(output) = (unsafe { output.as_mut() }) else {
        return -1;
    };
    let input = if length == 0 {
        &mut []
    } else {
        unsafe { core::slice::from_raw_parts_mut(data, length) }
    };
    let mut offset = 0;
    let mut remaining = length;
    let mut index = 0;
    while index < remaining && input[offset] == b'"' {
        offset += 1;
        remaining -= 1;
        index += 1;
    }
    while remaining > 0 && input[offset + remaining - 1] == b'"' {
        remaining -= 1;
        input[offset + remaining] = 0;
    }
    *output = Trimmed {
        offset,
        length: remaining,
    };
    0
}

/// # Safety
/// Data is initialized/writable for length bytes. ASCII transformations retain
/// the original state machine, including leading/consecutive hyphen behavior.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_response_key(data: *mut u8, length: usize) -> i32 {
    if length > isize::MAX as usize || (data.is_null() && length != 0) {
        return -1;
    }
    let input = if length == 0 {
        &mut []
    } else {
        unsafe { core::slice::from_raw_parts_mut(data, length) }
    };
    let mut initial = true;
    for byte in input {
        if initial {
            *byte = byte.to_ascii_uppercase();
            initial = false;
        } else if *byte == b'-' {
            initial = true;
        } else {
            *byte = byte.to_ascii_lowercase();
        }
    }
    0
}
