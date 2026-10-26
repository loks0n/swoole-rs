//! Complete inline cursor, mutable suffix and pointer-result publication.
use std::ffi::{CStr, c_char, c_void};
unsafe extern "C" {
    fn memcmp(a: *const c_void, b: *const c_void, count: usize) -> i32;
}

fn whitespace(byte: u8, signed_char: u8) -> bool {
    let promoted = if signed_char != 0 {
        i32::from(byte as i8)
    } else {
        i32::from(byte)
    };
    // SAFETY: callers guarantee each promoted byte is a defined isspace argument.
    unsafe { super::isspace(promoted) != 0 }
}

/// Trim and advance the caller's actual cursor, at each original publication.
/// # Safety
/// With length0 cursor need not be readable. Otherwise cursor is a writable
/// native char-pointer slot and each visited byte is readable, with defined
/// native isspace promotion. Caller owns its provenance and quiescence. No Rust
/// reference covers the slot/range or survives the host libc classification.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_ltrim(
    cursor: *mut *mut c_char,
    length: usize,
    signed_char: u8,
) -> usize {
    let mut skipped = 0;
    while skipped < length {
        // Keep the original short-circuit and fresh cursor observations. With `length > 0`
        // the slot is writable and every visited byte readable.
        // SAFETY: as above.
        let current = unsafe { cursor.read() };
        // SAFETY: as above.
        if unsafe { current.read() } == 0 {
            break;
        }
        // SAFETY: as above.
        let current = unsafe { cursor.read() };
        // SAFETY: as above.
        if !whitespace(unsafe { current.cast::<u8>().read() }, signed_char) {
            break;
        }
        // SAFETY: as above.
        let current = unsafe { cursor.read() };
        // SAFETY: as above.
        unsafe { cursor.write(current.wrapping_add(1)) };
        skipped += 1;
    }
    length - skipped
}

/// Mutable suffix trim: classify and clear each byte before visiting its left.
/// # Safety
/// Visited bytes are readable/writable with original native isspace promotions;
/// length0 accesses nothing (including null). Caller owns range and quiescence.
/// No allocation, pointer retention, callback or full-range Rust borrow.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_rtrim(
    data: *mut c_char,
    length: usize,
    signed_char: u8,
) -> usize {
    let mut kept = length;
    while kept != 0 {
        // Byte `kept - 1` is a visited byte: readable and writable per the contract.
        let byte = data.wrapping_add(kept - 1);
        // SAFETY: as above.
        if !whitespace(unsafe { byte.cast::<u8>().read() }, signed_char) {
            break;
        }
        // SAFETY: as above.
        unsafe { byte.write(0) };
        kept -= 1;
    }
    kept
}

/// Borrowed result facts only. Pointer derives from the input allocation;
/// offset-1 and null denote a miss. needle_length records native uint32 narrowing.
#[repr(C)]
pub struct SwrUtilsSearchResult {
    pub pointer: *const c_char,
    pub offset: isize,
    pub needle_length: u32,
}

/// Complete forward binary/casefold or reverse C-needle search and projection.
/// # Safety
/// Modes0/1 obey the original visited-byte/compared-range and nonempty-needle
/// contract. Mode2 reads a valid NUL-terminated needle first, narrows its size as
/// the original uint32 assignment, then requires length>=narrowed needle size.
/// Original reverse index0 omission and casefold first-byte guard remain.
/// Native debug assertions run after return; empty/narrowed-zero needle domains
/// and their assertion ordering remain unqualified. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_search(
    data: *const c_char,
    length: usize,
    needle: *const c_char,
    needle_length: u32,
    mode: u8,
) -> SwrUtilsSearchResult {
    let needle_length = if mode == 2 {
        // SAFETY: mode 2 requires a valid NUL-terminated needle.
        unsafe { CStr::from_ptr(needle) }.to_bytes().len() as u32
    } else {
        needle_length
    };
    // Match only the ranges the native loop actually observes. Do not form
    // slices spanning unused haystack/needle tails before an early result.
    let count = needle_length as usize;
    let mut offset = -1;
    if count != 0 && count <= length && mode <= 2 {
        let mut position = if mode == 2 { length - count } else { 0 };
        while if mode == 2 {
            position != 0
        } else {
            position <= length - count
        } {
            // `position + count <= length`, so `count` bytes from `current` lie in the
            // haystack, and the needle has `count` readable bytes.
            let current = data.wrapping_add(position);
            // SAFETY: as above.
            let first = unsafe { current.read() };
            // SAFETY: as above; `count != 0`.
            let first_matches = first == unsafe { needle.read() };
            let matched = first_matches
                && if mode == 1 {
                    // SAFETY: as above.
                    unsafe { super::strncasecmp(current, needle, count) == 0 }
                } else {
                    // SAFETY: as above.
                    unsafe { memcmp(current.cast(), needle.cast(), count) == 0 }
                };
            if matched {
                offset = position as isize;
                break;
            }
            if mode == 2 {
                position -= 1;
            } else {
                position += 1;
            }
        }
    }
    SwrUtilsSearchResult {
        pointer: if offset < 0 {
            std::ptr::null()
        } else {
            data.wrapping_add(offset as usize)
        },
        offset,
        needle_length,
    }
}
